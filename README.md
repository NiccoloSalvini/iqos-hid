# iqos-hid

Ascolto passivo del canale USB di una **IQOS ILUMA** dal Mac (o da Linux/Windows), per capire cosa il dispositivo comunica al computer.

> English: passive listener for the USB HID channel exposed by IQOS ILUMA devices. It only reads, never writes. Notes on the descriptor below.

Progetto indipendente, a scopo di studio. Non è affiliato né approvato da Philip Morris International. IQOS e ILUMA sono marchi dei rispettivi proprietari.

## Cosa espone il dispositivo

Rilevato su una **IQOS ILUMA i ONE** collegata via USB-C a macOS:

| Campo | Valore |
|---|---|
| Vendor ID | `0x2759` (Philip Morris Products S.A.) |
| Product ID | `0x0003` |
| `bcdDevice` | `0x0200` |
| Velocità | Full Speed (12 Mbit/s) |
| Interfacce | una, classe HID (3) |

Report descriptor:

```
06 00 ff        Usage Page (Vendor 0xFF00)
09 01           Usage (1)
a1 01           Collection (Application)
  85 3f         Report ID 0x3F
  95 3f 75 08   63 × 8 bit
  81 02         Input
  85 3f ...     Output, 63 byte
  a1 01         Collection
    85 40       Report ID 0x40
    ...         Input e Output, 63 byte
  c0
c0
```

Un canale proprietario a pacchetti da 63 byte, con due report ID. Il protocollo applicativo non è documentato. Non c'è una porta seriale e su macOS il dispositivo viene preso dal driver HID di sistema, quindi `pyusb` non serve: si usa `hidapi`.

## Uso

Serve [uv](https://docs.astral.sh/uv/), che installa da solo la dipendenza `hidapi`.

```sh
./iqos_hid.py list                     # dispositivi trovati (seriale mascherato)
./iqos_hid.py listen                   # stampa i report in arrivo, Ctrl+C per uscire
./iqos_hid.py listen --seconds 60 --log sessione.jsonl
```

Senza stimoli il dispositivo resta in silenzio (30 s di prova: zero report), quindi il canale sembra a domanda e risposta. Mentre ascolti, prova comunque a inserire uno stick, premere il tasto, staccare e riattaccare il cavo, e annota cosa succede.

Su Linux può servire una regola udev per leggere `/dev/hidraw*` senza root:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2759", MODE="0660", TAG+="uaccess"
```

## Sicurezza

Lo script **non scrive mai** sul dispositivo. Su un canale del genere passano probabilmente anche i comandi di aggiornamento firmware: mandare pacchetti a caso può bloccare la IQOS. Se vuoi contribuire con comandi, ricavali osservando il traffico degli strumenti ufficiali, non provando a caso.

## Contribuire

Sono utili soprattutto:

- descrittori e `bcdDevice` di altri modelli (ILUMA, ILUMA i, PRIME, ONE), con l'output di `./iqos_hid.py list`;
- log `--log` di eventi riconoscibili, con una nota su cosa stavi facendo.

Prima di condividere un log o un output, togli il numero di serie.

## Licenza

MIT
