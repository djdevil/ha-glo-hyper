"""glo_bond_clone: ripete su un secondo ESP32 l'abbinamento BLE di un altro ESP32.

Il glo Hyper ricorda un solo dispositivo abbinato e lo riconosce dall'indirizzo
pubblico e dalla chiave LTK. Questo componente, prima che il Bluetooth parta:

1. imposta il MAC Bluetooth uguale a quello dell'ESP abbinato;
2. scrive nella NVS la voce ``bt_config.conf/bt_cfg_key0`` copiata da quell'ESP.

ESPERIMENTO: due ESP con lo stesso MAC Bluetooth risultano a Home Assistant come
lo stesso scanner. Usare un solo ESP clonato acceso alla volta.
"""

from __future__ import annotations

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID

CODEOWNERS = ["@djdevil"]
DEPENDENCIES = ["esp32"]
AUTO_LOAD: list[str] = []

CONF_BT_MAC = "bt_mac"
CONF_BOND_HEX = "bond_hex"

glo_bond_clone_ns = cg.esphome_ns.namespace("glo_bond_clone")
GloBondClone = glo_bond_clone_ns.class_("GloBondClone", cg.Component)


def _bond_hex(value: object) -> str:
    """Esadecimale senza spazi, lunghezza pari, al massimo 4000 byte."""
    text: str = "".join(cv.string(value).split()).lower()
    if len(text) % 2 or any(c not in "0123456789abcdef" for c in text):
        raise cv.Invalid("bond_hex deve essere esadecimale (coppie di cifre)")
    if not 0 < len(text) // 2 <= 4000:
        raise cv.Invalid("bond_hex vuoto o troppo lungo")
    return text


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(GloBondClone),
        cv.Required(CONF_BT_MAC): cv.mac_address,
        cv.Required(CONF_BOND_HEX): _bond_hex,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config: dict) -> None:
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_bt_mac(config[CONF_BT_MAC].as_hex))
    bond: bytes = bytes.fromhex(config[CONF_BOND_HEX])
    cg.add(var.set_bond([cg.RawExpression(str(b)) for b in bond]))
