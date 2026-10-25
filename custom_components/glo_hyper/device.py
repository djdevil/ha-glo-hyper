"""Client BLE del glo Hyper Pro+."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from .protocol import (
    CHAR_BATTERY,
    CHAR_DEVICE_INFO,
    CHAR_FIND,
    CHAR_HEATING,
    CHAR_LIFECYCLE,
    CHAR_LOCK,
    CHAR_SESSION_STATUS,
    CHAR_TIME,
    NOTIFY_CHARACTERISTICS,
    Battery,
    DeviceInfo,
    HeatingMode,
    LifecycleStat,
    ProtocolError,
    SessionStatus,
    SessionStatusCommand,
    encode_find,
    encode_heating_mode,
    encode_lifecycle_request,
    encode_lock,
    encode_session_command,
    encode_time,
    parse_battery,
    parse_device_info,
    parse_heating_mode,
    parse_lifecycle_value,
    parse_lock,
    parse_session_status,
)

_LOGGER = logging.getLogger(__name__)

# Attesa massima della notifica con il valore di una statistica.
_STAT_TIMEOUT: float = 3.0
# Pausa dopo l'attivazione delle notifiche, prima della prima richiesta.
_STAT_SETTLE: float = 0.3


def _checked_incomplete(complete: int, incomplete: int, previous: GloData) -> int | None:
    """Scarta un valore delle interrotte copiato dalle complete.

    Se le due risposte sono identiche e le interrotte erano diverse, quasi
    certamente la seconda risposta è l'eco della prima: si tiene il valore noto.
    """
    known: int | None = previous.incomplete_sessions
    if incomplete == complete and known is not None and known != incomplete:
        _LOGGER.debug(
            "Sessioni interrotte = complete (%s), sospetto: mantenuto %s", incomplete, known
        )
        return known
    return incomplete


@dataclass(frozen=True, slots=True)
class GloData:
    """Istantanea dello stato del dispositivo."""

    battery: Battery | None = None
    status: SessionStatus | None = None
    heating_mode: HeatingMode | None = None
    locked: bool | None = None
    info: DeviceInfo | None = None
    complete_sessions: int | None = None
    incomplete_sessions: int | None = None
    last_seen: datetime | None = None


DataListener = Callable[[GloData], None]


class GloConnectionError(Exception):
    """Errore di connessione o comunicazione con il dispositivo."""


class GloDevice:
    """Gestisce connessione, letture, notifiche e comandi."""

    def __init__(
        self,
        ble_device: BLEDevice,
        persistent: bool,
        client_class: type[BleakClient] = BleakClientWithServiceCache,
    ) -> None:
        self._ble_device: BLEDevice = ble_device
        self._persistent: bool = persistent
        # Classe client: quella standard o una limitata agli adattatori scelti.
        self._client_class: type[BleakClient] = client_class
        self._client: BleakClient | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._data: GloData = GloData()
        self._listeners: list[DataListener] = []
        self._time_synced: bool = False
        # Ultimi byte grezzi per caratteristica (diagnostica) e letture anomale.
        self._raw: dict[str, str] = {}
        self._invalid_reads: int = 0
        self._notifying: bool = False

    @property
    def address(self) -> str:
        """Indirizzo BLE del dispositivo."""
        return self._ble_device.address

    @property
    def data(self) -> GloData:
        """Ultimo stato noto."""
        return self._data

    @property
    def is_connected(self) -> bool:
        """True se la connessione GATT è attiva."""
        return self._client is not None and self._client.is_connected

    @property
    def raw_values(self) -> dict[str, str]:
        """Ultimi valori grezzi letti, in esadecimale."""
        return dict(self._raw)

    @property
    def invalid_reads(self) -> int:
        """Numero di letture scartate perché anomale."""
        return self._invalid_reads

    def restore_data(self, data: GloData) -> None:
        """Riparte dall'ultimo stato salvato (prima di qualsiasi lettura)."""
        self._data = data

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Aggiorna il BLEDevice, che può cambiare adattatore o proxy."""
        self._ble_device = ble_device

    def add_listener(self, listener: DataListener) -> Callable[[], None]:
        """Registra un callback per i dati ricevuti via notifica."""
        self._listeners.append(listener)

        def _remove() -> None:
            self._listeners.remove(listener)

        return _remove

    # --- Connessione ------------------------------------------------------------
    def _on_disconnect(self, _: BleakClient) -> None:
        _LOGGER.debug("%s: disconnesso", self.address)
        self._client = None
        self._notifying = False

    def _should_stay_connected(self) -> bool:
        """Resta collegato solo con la connessione persistente attiva."""
        return self._persistent

    async def _finish(self, client: BleakClient) -> None:
        """Dopo una lettura o un comando: chiude o mantiene la connessione."""
        if self._should_stay_connected():
            if not self._notifying and client.is_connected:
                _LOGGER.debug("%s: connessione persistente", self.address)
                await self._start_notifications(client)
        else:
            await self._disconnect_unlocked()

    async def _ensure_connected(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client
        try:
            client: BleakClient = await establish_connection(
                self._client_class,
                self._ble_device,
                self._ble_device.name or self.address,
                disconnected_callback=self._on_disconnect,
                max_attempts=3,
                # Il glo accetta solo collegamenti cifrati (bonding), come fa
                # l'app myglo dopo la connessione. Con BlueZ il pairing avviene
                # prima della scoperta dei servizi; con un proxy ESPHome
                # (>= 2024.3) subito dopo il collegamento, prima dei servizi.
                # Se il dispositivo è già abbinato, BlueZ salta il passaggio.
                pair=True,
            )
        except NotImplementedError as err:
            raise GloConnectionError(
                f"Il proxy Bluetooth non supporta il pairing: aggiorna ESPHome ({err})"
            ) from err
        except (BleakError, TimeoutError) as err:
            raise GloConnectionError(f"Connessione fallita: {err}") from err
        self._client = client
        self._notifying = False
        return client

    async def _start_notifications(self, client: BleakClient) -> None:
        self._notifying = True
        for uuid in NOTIFY_CHARACTERISTICS:
            try:
                await client.start_notify(uuid, self._handle_notification)
            except BleakError as err:
                _LOGGER.warning("%s: notifiche non attivate su %s: %s", self.address, uuid, err)

    async def async_disconnect(self) -> None:
        """Chiude la connessione, se aperta."""
        async with self._lock:
            await self._disconnect_unlocked()

    async def _disconnect_unlocked(self) -> None:
        client: BleakClient | None = self._client
        self._client = None
        self._notifying = False
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except BleakError as err:
                _LOGGER.debug("%s: errore in disconnessione: %s", self.address, err)

    # --- Notifiche ----------------------------------------------------------------
    def _handle_notification(self, char: BleakGATTCharacteristic, payload: bytearray) -> None:
        raw: bytes = bytes(payload)
        uuid: str = char.uuid.lower()
        self._raw[uuid] = raw.hex()
        try:
            if uuid == CHAR_BATTERY:
                self._data = replace(self._data, battery=parse_battery(raw))
            elif uuid == CHAR_SESSION_STATUS:
                self._data = replace(self._data, status=parse_session_status(raw))
            elif uuid == CHAR_HEATING:
                self._data = replace(self._data, heating_mode=parse_heating_mode(raw))
            elif uuid == CHAR_LOCK:
                self._data = replace(self._data, locked=parse_lock(raw))
            else:
                return
            self._data = replace(self._data, last_seen=datetime.now(UTC))
        except ProtocolError as err:
            # Le risposte ai comandi possono avere un formato diverso: si ignorano.
            _LOGGER.debug("%s: notifica ignorata su %s: %s", self.address, uuid, err)
            return
        for listener in list(self._listeners):
            listener(self._data)

    # --- Letture ------------------------------------------------------------------
    async def _read(self, client: BleakClient, uuid: str) -> bytes:
        return bytes(await client.read_gatt_char(uuid))

    async def _read_parsed[T](
        self,
        client: BleakClient,
        uuid: str,
        parser: Callable[[bytes], T],
        previous: T | None,
    ) -> T | None:
        """Legge e interpreta una caratteristica, tollerando risposte anomale.

        Un valore non valido (es. una risposta scambiata dal proxy) non fa
        fallire l'intera lettura: si riprova una volta e, se resta anomalo,
        si mantiene l'ultimo valore buono.
        """
        for attempt in (1, 2):
            raw: bytes = await self._read(client, uuid)
            self._raw[uuid] = raw.hex()
            try:
                return parser(raw)
            except ProtocolError as err:
                _LOGGER.debug(
                    "%s: valore anomalo su %s (tentativo %s): %s",
                    self.address,
                    uuid,
                    attempt,
                    err,
                )
        self._invalid_reads += 1
        return previous

    async def async_update(self) -> GloData:
        """Legge tutte le caratteristiche principali."""
        async with self._lock:
            try:
                client: BleakClient = await self._ensure_connected()
                current: GloData = self._data
                data: GloData = replace(
                    current,
                    battery=await self._read_parsed(
                        client, CHAR_BATTERY, parse_battery, current.battery
                    ),
                    status=await self._read_parsed(
                        client, CHAR_SESSION_STATUS, parse_session_status, current.status
                    ),
                    heating_mode=await self._read_parsed(
                        client, CHAR_HEATING, parse_heating_mode, current.heating_mode
                    ),
                    locked=await self._read_parsed(
                        client, CHAR_LOCK, parse_lock, current.locked
                    ),
                )
                if data.info is None:
                    data = replace(data, info=await self._read_info(client))
                if not self._time_synced:
                    await self._sync_time(client)
                data = await self._read_session_counters(client, data)
                data = replace(data, last_seen=datetime.now(UTC))
                await self._finish(client)
            except (BleakError, TimeoutError) as err:
                await self._disconnect_unlocked()
                raise GloConnectionError(f"Lettura fallita: {err}") from err
            self._data = data
            return data

    async def _read_stat(
        self, client: BleakClient, queue: asyncio.Queue[bytes], stat: LifecycleStat
    ) -> int:
        """Scrive la richiesta e prende la prima notifica arrivata DOPO di essa.

        La risposta non contiene il numero della statistica: le notifiche
        arrivate prima della richiesta (es. il valore precedente rimandato
        all'attivazione delle notifiche) vanno scartate.
        """
        while not queue.empty():
            stale: bytes = queue.get_nowait()
            _LOGGER.debug("%s: notifica statistiche scartata: %s", self.address, stale.hex())
        await client.write_gatt_char(
            CHAR_LIFECYCLE, encode_lifecycle_request(stat), response=True
        )
        raw: bytes = await asyncio.wait_for(queue.get(), _STAT_TIMEOUT)
        self._raw[f"{CHAR_LIFECYCLE}#{stat.value}"] = raw.hex()
        return parse_lifecycle_value(raw)

    async def _read_session_counters(self, client: BleakClient, data: GloData) -> GloData:
        """Contatori totali delle sessioni: un errore qui non blocca le altre letture."""
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def _on_value(_: BleakGATTCharacteristic, payload: bytearray) -> None:
            queue.put_nowait(bytes(payload))

        try:
            await client.start_notify(CHAR_LIFECYCLE, _on_value)
            try:
                # Lascia arrivare un eventuale valore rimandato all'attivazione.
                await asyncio.sleep(_STAT_SETTLE)
                complete: int = await self._read_stat(
                    client, queue, LifecycleStat.COMPLETE_SESSIONS
                )
                incomplete: int = await self._read_stat(
                    client, queue, LifecycleStat.INCOMPLETE_SESSIONS
                )
            finally:
                try:
                    await client.stop_notify(CHAR_LIFECYCLE)
                except BleakError as err:
                    _LOGGER.debug("%s: stop_notify statistiche: %s", self.address, err)
        except (BleakError, TimeoutError, ProtocolError) as err:
            _LOGGER.debug("%s: contatori sessioni non letti: %s", self.address, err)
            return data
        return replace(
            data,
            complete_sessions=complete,
            incomplete_sessions=_checked_incomplete(complete, incomplete, data),
        )

    async def _read_info(self, client: BleakClient) -> DeviceInfo | None:
        raw: bytes = await self._read(client, CHAR_DEVICE_INFO)
        try:
            return parse_device_info(raw)
        except ProtocolError:
            _LOGGER.debug("%s: device info non decodificata: %s", self.address, raw.hex())
            return None

    async def _sync_time(self, client: BleakClient) -> None:
        # L'app myglo imposta l'orologio a ogni connessione; serve per lo storico.
        try:
            await client.write_gatt_char(CHAR_TIME, encode_time(int(time.time())), response=True)
            self._time_synced = True
        except BleakError as err:
            _LOGGER.debug("%s: sincronizzazione ora fallita: %s", self.address, err)

    # --- Comandi ------------------------------------------------------------------
    async def _write(self, uuid: str, payload: bytes) -> GloData:
        async with self._lock:
            try:
                client: BleakClient = await self._ensure_connected()
                await client.write_gatt_char(uuid, payload, response=True)
                # Rilettura per confermare il nuovo stato.
                if uuid == CHAR_HEATING:
                    mode: HeatingMode = parse_heating_mode(await self._read(client, uuid))
                    self._data = replace(self._data, heating_mode=mode)
                elif uuid == CHAR_LOCK:
                    self._data = replace(self._data, locked=parse_lock(await self._read(client, uuid)))
                elif uuid == CHAR_SESSION_STATUS:
                    status: SessionStatus = parse_session_status(await self._read(client, uuid))
                    self._data = replace(self._data, status=status)
            except (BleakError, TimeoutError) as err:
                await self._disconnect_unlocked()
                raise GloConnectionError(f"Comando fallito: {err}") from err
            except ProtocolError as err:
                raise GloConnectionError(f"Conferma non valida: {err}") from err
            finally:
                if self._client is not None:
                    await self._finish(self._client)
            return self._data

    async def async_set_heating_mode(self, mode: HeatingMode) -> GloData:
        """Imposta Standard o Boost."""
        return await self._write(CHAR_HEATING, encode_heating_mode(mode))

    async def async_set_auto_start(self, enabled: bool) -> GloData:
        """Attiva o disattiva l'auto-start."""
        return await self._write(
            CHAR_SESSION_STATUS,
            encode_session_command(SessionStatusCommand.AUTO_START, enabled),
        )

    async def async_set_auto_stop(self, enabled: bool) -> GloData:
        """Attiva o disattiva l'auto-stop."""
        return await self._write(
            CHAR_SESSION_STATUS,
            encode_session_command(SessionStatusCommand.AUTO_STOP, enabled),
        )

    async def async_set_locked(self, locked: bool) -> GloData:
        """Blocca o sblocca il dispositivo."""
        return await self._write(CHAR_LOCK, encode_lock(locked))

    async def async_find(self, seconds: int) -> GloData:
        """Fa vibrare/suonare il dispositivo per ``seconds`` secondi."""
        return await self._write(CHAR_FIND, encode_find(True, seconds))
