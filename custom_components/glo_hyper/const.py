"""Costanti dell'integrazione glo Hyper."""

from __future__ import annotations

from typing import Final

DOMAIN: Final[str] = "glo_hyper"
MANUFACTURER: Final[str] = "BAT"
MODEL: Final[str] = "glo Hyper Pro+"

CONF_PERSISTENT: Final[str] = "persistent_connection"
CONF_SCAN_INTERVAL: Final[str] = "scan_interval"
# Adattatori Bluetooth (source) da usare; lista vuota = tutti.
CONF_ADAPTERS: Final[str] = "adapters"
# Fascia notturna: inizio, fine (HH:MM:SS) e intervallo in minuti (0 = spenta).
CONF_NIGHT_START: Final[str] = "night_start"
CONF_NIGHT_END: Final[str] = "night_end"
CONF_NIGHT_INTERVAL: Final[str] = "night_interval"

# Senza connessione persistente: lettura periodica e poi disconnessione,
# così l'app myglo resta utilizzabile e il dispositivo consuma meno.
DEFAULT_PERSISTENT: Final[bool] = False
DEFAULT_SCAN_INTERVAL: Final[int] = 300
MIN_SCAN_INTERVAL: Final[int] = 30
MAX_SCAN_INTERVAL: Final[int] = 3600
# Durante una sessione si legge più spesso per cogliere subito la fine.
SESSION_SCAN_INTERVAL: Final[int] = 30

DEFAULT_NIGHT_START: Final[str] = "23:00:00"
DEFAULT_NIGHT_END: Final[str] = "07:00:00"
DEFAULT_NIGHT_INTERVAL: Final[int] = 60
MAX_NIGHT_INTERVAL: Final[int] = 480

FIND_DURATION_SECONDS: Final[int] = 10
