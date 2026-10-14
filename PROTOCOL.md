# Protocollo USB della IQOS ILUMA i ONE

Ricavato il 14 ottobre 2026 registrando il traffico WebHID della WebApp ufficiale (`it.iqos.com/it/webapp`) mentre si cambiavano le impostazioni. I pacchetti grezzi sono in [`captures/`](captures/). Firmware `bcdDevice` 0x0200.

## Da dove vengono i comandi

La WebApp non costruisce i comandi: li riceve dal backend IQOS e li inoltra alla IQOS. Analisi statica del bundle `iqos-connect.rrp-backend.com/static/js/main.275fcf4a.js` (con REA `analyze-javascript-application` più lettura mirata del codice):

- le impostazioni passano per l'API cloud `/asset/{id}/device/actions/updateSetting`; i frame arrivano dal server con `request_id`, `transfer_data` e `token`, e il browser li mette in coda e li scrive con `sendReport`;
- nel bundle sono cablati solo pochi frame fissi, tra cui il ping (`00C0010015`, cioè una lettura senza payload del registro `0x001` su `0xC0`, CRC compreso) e i suoi equivalenti su `0xC9`;
- i nomi delle impostazioni che il backend sa gestire sono: `parentProtection` (blocco), `ledIntensity`, `extHapticProfile` (tabella eventi), `heatingVibration`, `uiHeatingVibration`, `batteryChargedVibration`, `uiBatteryChargedVibration`, `liftUpGesture`, `doubleTapGesture`, `autoStartHeating`, `pauseHeating`, `sessionProfiling`, `adaptiveExpManagement` (FlexBattery), `responsiveDrawProfile` (FlexPuff), `vapeCloudSize`, `engineJoule`.

Quindi il significato dei registri, compresi i byte LED, non è nel JavaScript: si ricava solo dal traffico.

## Trasporto

Interfaccia HID, usage page `0xFF00`. Richieste e risposte viaggiano sul **report `0x3F`** (63 byte, zero di riempimento). Il report `0x40` non è usato dalla WebApp. Il dispositivo non manda nulla di sua iniziativa: risponde solo alle richieste.

Nelle risposte i byte dopo il CRC sono residui del buffer e vanno ignorati.

## Messaggio

```
[len] [net] [b1] [b2] [payload ...] [crc]
```

| Campo | Significato |
|---|---|
| `len` | byte che seguono: `net` + `b1` + `b2` + payload + `crc` |
| `net` | `0xC0` (la WebApp usa solo questo; IQOS Scope legge anche da `0xC9`) |
| `b1` bit 7-6 | operazione: `00` lettura, `01` scrittura, `10` risposta a lettura, `11` conferma di scrittura |
| `b1` bit 3-2 | lunghezza del payload: `0` → 0, `1` → 4, `2` → 14, `3` → 24 byte |
| `b1` bit 1-0 + `b2` | indirizzo del registro a 10 bit: `S = b2 << 2 \| (b1 & 3)` |
| `crc` | CRC-8, polinomio `0x07`, init `0x00`, su `b1` … fine payload (`net` escluso) |

Esempio, scrittura della luminosità a 30:

```
08 | c0 | 44 24 | 1e 00 00 00 | 9a
```

## Registri

| Registro `S` | `b1 b2` (lettura) | Contenuto | Valori visti |
|---|---|---|---|
| `0x090` | `00 24` | luminosità LED, u32 little-endian, percentuale | `30` bassa, `100` alta; `60` accettato |
| `0x010` | `00 04` | blocco del dispositivo | `00 00 00 00` sbloccato, `02 ff 00 00` bloccato |
| `0x093` | `07 24` + chiave | tabella; chiave `01` = avvio automatico | payload `01 vv 00 00`, `vv` = `00` off, `01` on |
| `0x013` | `07 04` + chiave | tabella degli eventi (vibrazione e LED) | vedi sotto |

I registri con i due bit bassi a `3` sono tabelle: la lettura manda una chiave da 4 byte (`chiave 00 00 00`) e la risposta contiene la voce.

IQOS Scope legge la batteria da `S = 0x090`, lo stesso registro che la WebApp scrive come luminosità e che rilegge subito dopo. Uno dei due va verificato.

## Tabella degli eventi (`S = 0x013`)

Voce letta (14 byte):

```
id 00 01 04 00 | p1 p2 p3 p4 | 01 01 | vib | 00 00
```

| `id` | Evento nella WebApp |
|---|---|
| `0x0C` | avvio del riscaldamento |
| `0x0E` | pronto all'uso |
| `0x0D` | quasi finito |
| `0x0F` | esperienza finita |
| `0x0B` | sconosciuto (`00 00 00 00 2b 2b 2b 2b`), riscritto sempre uguale |

- `vib`: `0x1D` vibrazione attiva, `0x01` spenta.
- `p1..p4`: diversi per evento e mai cambiati dalla WebApp (`13 14 15 16`, `04 01 01 01`, `02 02 02 02`, `07 01 01 01`). Probabilmente l'animazione dei LED associata all'evento: **non verificato**.

In scrittura la voce è preceduta da un byte di controllo e perde l'ultimo zero:

```
payload = [chk] + voce[0:13]
chk     = CRC-8(poly 0x07, init 0x7B) su voce[0:12]
```

La WebApp riscrive sempre tutte e cinque le voci (`0C 0E 0D 0F 0B`), poi conferma con una scrittura da 4 byte `00 ff ff 00` sullo stesso registro, e infine le rilegge.

## Cose che non passano dal dispositivo

Il nome del dispositivo («Rinomina») è salvato solo sull'account IQOS: nessun pacchetto USB.

## Non esplorato

Aggiornamento firmware, ripristino e disaccoppiamento non sono stati toccati.
