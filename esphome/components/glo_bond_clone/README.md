# glo_bond_clone (sperimentale)

Il glo Hyper ricorda **un solo** dispositivo abbinato. Questo external component
ESPHome fa sì che un secondo ESP32 si presenti al glo come quello già abbinato:

1. imposta il MAC Bluetooth uguale a quello dell'ESP abbinato;
2. scrive nella NVS la voce `bt_config.conf/bt_cfg_key0` copiata da quell'ESP.

Agisce nel `setup()` con priorità `HARDWARE`, prima che ESPHome accenda il
Bluetooth (che avviene nel `loop()`).

## Uso

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/djdevil/ha-glo-hyper
      ref: esp-bond-clone
      path: esphome/components
    components: [glo_bond_clone]

glo_bond_clone:
  bt_mac: "E8:6B:EA:D4:80:E2"      # MAC Bluetooth dell'ESP abbinato
  bond_hex: !secret glo_bond_hex   # contenuto di bt_cfg_key0 in esadecimale
```

`bond_hex` contiene le chiavi dell'abbinamento: tenerlo in `secrets.yaml`, mai nel
repository. Si ricava leggendo la partizione NVS dell'ESP abbinato con
`esptool read-flash` e decodificandola.

Opzione `report_real_mac` (predefinita `true`): a Home Assistant viene comunicato
il MAC Bluetooth vero del chip, mentre la radio usa quello clonato verso il glo.
Così più ESP clonati restano scanner distinti e possono stare accesi insieme.
Funziona sostituendo al linker `esp_bt_dev_get_address()`, che ESPHome usa solo
per riportare il MAC dell'adattatore.

## Limiti

- Se `report_real_mac` è `false`, Home Assistant vede gli ESP clonati come lo
  stesso scanner: tenerne acceso uno solo alla volta.
- Se il glo viene riabbinato (5 pressioni, app myglo, reset) le chiavi cambiano e
  `bond_hex` va aggiornato.
