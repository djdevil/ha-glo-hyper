# glo Hyper per Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/djdevil/ha-glo-hyper/actions/workflows/validate.yml/badge.svg)](https://github.com/djdevil/ha-glo-hyper/actions/workflows/validate.yml)
[![Tests](https://github.com/djdevil/ha-glo-hyper/actions/workflows/tests.yml/badge.svg)](https://github.com/djdevil/ha-glo-hyper/actions/workflows/tests.yml)

Integrazione custom per collegare il **glo Hyper Pro+** a Home Assistant via **Bluetooth LE**, in locale e senza cloud.

> ⚠️ Progetto **non ufficiale**, non affiliato né approvato da BAT. "glo" è un marchio dei rispettivi proprietari. Si usa a proprio rischio.

🇬🇧 *[English version](README.md)*

---

## Funzioni

| Tipo | Entità |
|---|---|
| Sensori | Batteria (%), Sessioni rimanenti, Ricarica, Stato sessione, Stato dispositivo, Stick, Sessioni dall'ultima pulizia, **Sessioni totali**, Sessioni interrotte, Ultimo contatto, Soglia pulizia |
| Sensori binari | In carica, Sessione attiva, Stick inserito, Pulizia necessaria |
| Interruttori | Auto-start, Auto-stop |
| Lock | Blocco del dispositivo |
| Select | Modalità (Standard / Boost) |
| Pulsante | Trova il mio glo |

Altre caratteristiche:

- **Lettura periodica** senza tenere occupato il glo, così l'app myglo resta utilizzabile.
- Letture **ogni 30 s durante una sessione**, per registrare subito la fine.
- **Fascia notturna** con un intervallo di lettura più lungo.
- **Ultimi valori mantenuti** quando il glo è fuori portata e dopo un riavvio di Home Assistant.
- **Lettura immediata** appena il glo torna in portata.
- Scelta degli **adattatori Bluetooth** da usare (il glo accetta solo quelli abbinati).
- **Diagnostica** scaricabile, con i valori grezzi letti.

Dispositivo testato: **glo Hyper Pro+** (nome Bluetooth `Hyper Pro+ XXXX`).

## Requisiti

- Home Assistant **2025.1** o successivo con l'integrazione **Bluetooth** attiva. Le icone dell'integrazione compaiono dalla versione 2026.3.
- Un **proxy Bluetooth ESPHome** con connessioni attive. È la soluzione consigliata: è quella testata per l'abbinamento.
  ```yaml
  bluetooth_proxy:
    active: true
  ```
  Un adattatore Bluetooth locale può funzionare, ma con alcuni dongle l'abbinamento fallisce.

## Installazione

### HACS
1. In HACS apri il menu ⋮ e scegli **Repository personalizzati**.
2. Inserisci `https://github.com/djdevil/ha-glo-hyper` e scegli la categoria **Integration**.
3. Installa **glo Hyper** e riavvia Home Assistant.

### Manuale
Copia la cartella `custom_components/glo_hyper` in `/config/custom_components/` e riavvia Home Assistant.

## Primo collegamento (abbinamento)

Il glo accetta connessioni **solo dai dispositivi con cui è abbinato**. La prima volta devi metterlo in modalità pairing.

1. Porta il glo **vicino al proxy ESP32**.
2. Premi **5 volte** velocemente il tasto: sul display compare l'icona Bluetooth.
3. Il glo compare tra i dispositivi rilevati. Se non compare, vai in *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → glo Hyper*.
4. Conferma: Home Assistant si collega e si abbina.

Dopo il primo abbinamento il collegamento funziona senza ripetere la procedura.
Il glo può restare abbinato anche all'iPhone e all'app myglo. Si collega **un solo dispositivo alla volta**.

## Opzioni

Le trovi in *Impostazioni → Dispositivi e servizi → glo Hyper → Configura*.

| Opzione | Predefinito | Effetto |
|---|---|---|
| Adattatori Bluetooth da usare | tutti | Seleziona **solo** gli adattatori abbinati al glo, ad esempio il proxy ESP32. Così Home Assistant non prova quelli che il glo rifiuta |
| Connessione persistente | Off | **Off:** legge e si scollega. **On:** resta collegato e riceve gli eventi in tempo reale, ma l'app myglo non può collegarsi |
| Intervallo di lettura | 300 s | Da 30 a 3600 s |
| Fascia notturna: inizio / fine | 23:00 / 07:00 | Orari della fascia; può attraversare la mezzanotte |
| Fascia notturna: intervallo | 60 min | Ogni quanto leggere il glo nella fascia. **0 = fascia disattivata** |

> 💡 Ogni lettura "risveglia" il glo, e **quando è in carica vibra** a ogni risveglio. Se lo lasci in carica di notte, usa la fascia notturna.

## Contare le sigarette

`Sessioni totali` è il contatore delle sessioni **complete** registrate dal dispositivo e non si azzera mai. Per avere i conteggi giornalieri, settimanali o mensili usa un **utility meter**:

```yaml
utility_meter:
  glo_sessioni_giornaliere:
    source: sensor.hyper_pro_1234_sessioni_totali
    cycle: daily
```

## Scheda per la dashboard

In [`dashboard/glo_card_example.yaml`](dashboard/glo_card_example.yaml) trovi una scheda di esempio con batteria, stato della sessione, pulizia, comandi e grafico della batteria. Richiede [button-card](https://github.com/custom-cards/button-card), [mini-graph-card](https://github.com/kalkih/mini-graph-card) e [card-mod](https://github.com/thomasloven/lovelace-card-mod).

## Sicurezza

Per scelta **non sono esposti** il factory reset, l'azzeramento delle statistiche, l'aggiornamento firmware (OTA) e i comandi di gestione del dispositivo.

## Problemi comuni

| Problema | Soluzione |
|---|---|
| Non si collega / `Connection failed` | Il glo non è abbinato a quell'adattatore: ripeti l'abbinamento (5 pressioni) vicino all'ESP32 e seleziona solo l'ESP32 nelle opzioni |
| Entità ferme | Il glo è fuori portata: i valori restano gli ultimi letti, e "Ultimo contatto" indica quando è stato letto l'ultima volta |
| L'app myglo non si collega | Disattiva la connessione persistente, oppure chiudi Home Assistant per un momento |
| Vibra in carica | Usa la fascia notturna con un intervallo lungo |

Per segnalare un problema apri una [issue](https://github.com/djdevil/ha-glo-hyper/issues) allegando la **diagnostica**: dalla pagina dell'integrazione, menu ⋮ → *Scarica diagnostica*. Il numero di serie viene oscurato.

## Strumento di test da PC

```bash
pip install bleak
python tools/glo_test.py scan
python tools/glo_test.py read
python tools/glo_test.py watch
```

## Sviluppo

```bash
pip install -r requirements_test.txt
pytest tests
mypy --strict custom_components/glo_hyper
ruff check custom_components
```

---

## Licenza

[MIT](LICENSE)
