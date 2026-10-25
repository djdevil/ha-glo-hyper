# glo Hyper for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/djdevil/ha-glo-hyper/actions/workflows/validate.yml/badge.svg)](https://github.com/djdevil/ha-glo-hyper/actions/workflows/validate.yml)
[![Tests](https://github.com/djdevil/ha-glo-hyper/actions/workflows/tests.yml/badge.svg)](https://github.com/djdevil/ha-glo-hyper/actions/workflows/tests.yml)

Custom integration that connects the **glo Hyper Pro+** to Home Assistant over **Bluetooth LE**. It works locally, without the cloud.

> ⚠️ **Unofficial** project, not affiliated with or endorsed by BAT. "glo" is a trademark of its respective owners. Use at your own risk.

🇮🇹 *[Versione italiana](README.it.md)*

---

## Features

| Type | Entities |
|---|---|
| Sensors | Battery (%), Remaining sessions, Charging, Session state, Device state, Stick, Sessions since last cleaning, **Total sessions**, Interrupted sessions, Last seen, Cleaning threshold |
| Binary sensors | Charging, Session active, Stick inserted, Cleaning needed |
| Switches | Auto-start, Auto-stop |
| Lock | Device lock |
| Select | Mode (Standard / Boost) |
| Button | Find my glo |

Other features:

- **Periodic polling** that does not keep the glo busy, so the myglo app stays usable.
- Polling **every 30 s during a session**, so the end of the session is caught right away.
- **Night window** with a longer polling interval.
- **Last values are kept** while the glo is out of range and after a Home Assistant restart.
- **Immediate read** as soon as the glo comes back in range.
- Choice of the **Bluetooth adapters** to use, since the glo only accepts the ones it is paired with.
- Downloadable **diagnostics** with the raw values read from the device.

Tested device: **glo Hyper Pro+** (Bluetooth name `Hyper Pro+ XXXX`).

The entity names are translated into English and Italian.

## Requirements

- Home Assistant **2025.1** or later with the **Bluetooth** integration enabled. The integration icons appear from 2026.3.
- An **ESPHome Bluetooth proxy** with active connections. This is the recommended setup, and the one tested for pairing.
  ```yaml
  bluetooth_proxy:
    active: true
  ```
  A local Bluetooth adapter may work, but pairing fails with some dongles.

## Installation

### HACS
1. In HACS, open the ⋮ menu and choose **Custom repositories**.
2. Add `https://github.com/djdevil/ha-glo-hyper` with the category **Integration**.
3. Install **glo Hyper** and restart Home Assistant.

### Manual
Copy the `custom_components/glo_hyper` folder into `/config/custom_components/` and restart Home Assistant.

## First connection (pairing)

The glo only accepts connections **from devices it is paired with**. The first time, you need to put it in pairing mode.

1. Bring the glo **close to the ESP32 proxy**.
2. Press the button **5 times** quickly. The Bluetooth icon appears on the display.
3. The glo shows up among the discovered devices. If it doesn't, go to *Settings → Devices & services → Add integration → glo Hyper*.
4. Confirm. Home Assistant connects and pairs.

After the first pairing, the connection works without repeating these steps.
The glo can stay paired with your phone and the myglo app as well, but it accepts **only one connection at a time**.

## Options

You can find them in *Settings → Devices & services → glo Hyper → Configure*.

| Option | Default | Effect |
|---|---|---|
| Bluetooth adapters to use | all | Select **only** the adapters paired with the glo, such as the ESP32 proxy, so Home Assistant does not try adapters the glo rejects |
| Persistent connection | Off | **Off:** read, then disconnect. **On:** stay connected and receive events in real time, but the myglo app cannot connect |
| Polling interval | 300 s | From 30 to 3600 s |
| Night window: start / end | 23:00 / 07:00 | Window times. The window can cross midnight |
| Night window: interval | 60 min | How often to read the glo inside the window. **0 = window disabled** |

> 💡 Every read wakes the glo up, and **while charging it vibrates** each time. If you leave it charging overnight, use the night window.

## Counting sticks

`Total sessions` is the device's counter of **completed** sessions and is never reset. For daily, weekly or monthly counts, use a **utility meter**:

```yaml
utility_meter:
  glo_daily_sessions:
    source: sensor.hyper_pro_1234_total_sessions
    cycle: daily
```

Use the entity ID shown in your installation, which depends on the device name and the language.

## Dashboard card

[`dashboard/glo_card_example.yaml`](dashboard/glo_card_example.yaml) contains an example card with battery, session state, cleaning, controls and a battery graph. It requires [button-card](https://github.com/custom-cards/button-card), [mini-graph-card](https://github.com/kalkih/mini-graph-card) and [card-mod](https://github.com/thomasloven/lovelace-card-mod). Its labels are in Italian.

## Safety

Factory reset, statistics reset, firmware update (OTA) and device-management commands are **not exposed** on purpose.

## Troubleshooting

| Problem | Solution |
|---|---|
| It does not connect / `Connection failed` | The glo is not paired with that adapter. Pair it again (5 presses) close to the ESP32 and select only the ESP32 in the options |
| Entities stop updating | The glo is out of range. The entities keep the last values, and "Last seen" shows when it was last read |
| The myglo app cannot connect | Turn off the persistent connection, or disable the integration for a moment |
| It vibrates while charging | Use the night window with a long interval |

To report a problem, open an [issue](https://github.com/djdevil/ha-glo-hyper/issues) and attach the **diagnostics**: on the integration page, open the ⋮ menu → *Download diagnostics*. The serial number is redacted.

## PC test tool

```bash
pip install bleak
python tools/glo_test.py scan
python tools/glo_test.py read
python tools/glo_test.py watch
```

## Development

```bash
pip install -r requirements_test.txt
pytest tests
mypy --strict custom_components/glo_hyper
ruff check custom_components
```

## License

[MIT](LICENSE)
