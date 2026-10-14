# iqos-hid

Legge e cambia le impostazioni di una **IQOS ILUMA** via USB, dal terminale: luminosità (anche valori che l'app non offre), blocco, avvio automatico, vibrazione per evento.

> English: command-line tool to read and change IQOS ILUMA settings over USB HID. The protocol was captured from the official web app; see [PROTOCOL.md](PROTOCOL.md).

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

Un canale proprietario a pacchetti da 63 byte. Il formato dei messaggi e i registri sono in [PROTOCOL.md](PROTOCOL.md). Su macOS il dispositivo viene preso dal driver HID di sistema, quindi `pyusb` non serve: si usa `hidapi`.

## Uso

Serve [uv](https://docs.astral.sh/uv/), che installa da solo la dipendenza `hidapi`.

```sh
./iqos_hid.py list                          # dispositivi trovati (seriale mascherato)
./iqos_hid.py status                        # impostazioni attuali
./iqos_hid.py set brightness 60             # 1-100; l'app offre solo 30 e 100
./iqos_hid.py set autostart off
./iqos_hid.py set lock on                   # e poi: set lock off
./iqos_hid.py set vibration finito=on       # riscaldamento | pronto | quasi-finito | finito
./iqos_hid.py listen --log sessione.jsonl   # ascolto passivo
```

```
$ ./iqos_hid.py status
batteria        100%  4248 mV  28 °C  (decodifica ipotetica)
luminosità      100%
blocco          no
avvio automatico on
vibrazione riscaldamento on   LED 13 14 15 16
vibrazione pronto        on   LED 04 01 01 01
vibrazione quasi-finito  on   LED 02 02 02 02
vibrazione finito        off  LED 07 01 01 01
```

Ogni `set` rilegge il valore dal dispositivo e stampa quello effettivo.

Il dispositivo non manda nulla di sua iniziativa, quindi `listen` da solo resta muto.

Su Linux può servire una regola udev per leggere `/dev/hidraw*` senza root:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2759", MODE="0660", TAG+="uaccess"
```

## Sicurezza

Lo script scrive **solo** nei registri che la WebApp ufficiale scrive, con lo stesso formato, e non ha un comando per scrivere registri arbitrari. Su questo canale passano probabilmente anche aggiornamento firmware e ripristino: mandare pacchetti a caso può bloccare la IQOS. Nuovi comandi vanno ricavati dal traffico degli strumenti ufficiali, non provando a caso.

Testato su una sola IQOS ILUMA i ONE, firmware `0x0200`.

## Lavori correlati

[IQOS Scope](https://github.com/SabriEzzine/iqos-scope) è una dashboard WebHID che legge batteria, contatori e impostazioni dello stesso modello.

## Contribuire

Sono utili soprattutto:

- descrittori e `bcdDevice` di altri modelli (ILUMA, ILUMA i, PRIME, ONE), con l'output di `./iqos_hid.py list`;
- catture della WebApp ufficiale su altri modelli o firmware;
- il significato dei byte `p1..p4` nella tabella degli eventi (vedi [PROTOCOL.md](PROTOCOL.md)).

Prima di condividere un log o un output, togli il numero di serie.

## Licenza

MIT
