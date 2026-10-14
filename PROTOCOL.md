# Protocollo USB della IQOS ILUMA i ONE

Ricavato il 14 ottobre 2026 registrando il traffico WebHID della WebApp ufficiale (`it.iqos.com/it/webapp`) mentre si cambiavano le impostazioni. I pacchetti grezzi sono in [`captures/`](captures/). Firmware `bcdDevice` 0x0200.

## Da dove vengono i comandi

La WebApp non costruisce i comandi: li riceve dal backend IQOS e li inoltra alla IQOS. Analisi statica del bundle `iqos-connect.rrp-backend.com/static/js/main.275fcf4a.js` (con REA `analyze-javascript-application` più lettura mirata del codice):

- le impostazioni passano per l'API cloud `/asset/{id}/device/actions/updateSetting`; i frame arrivano dal server con `request_id`, `transfer_data` e `token`, e il browser li mette in coda e li scrive con `sendReport`;
- nel bundle sono cablati solo pochi frame fissi, tra cui il ping (`00C0010015`, cioè una lettura senza payload del registro `0x001` su `0xC0`, CRC compreso) e i suoi equivalenti su `0xC9`;
- i nomi delle impostazioni che il backend sa gestire sono: `parentProtection` (blocco), `ledIntensity`, `extHapticProfile` (tabella eventi), `heatingVibration`, `uiHeatingVibration`, `batteryChargedVibration`, `uiBatteryChargedVibration`, `liftUpGesture`, `doubleTapGesture`, `autoStartHeating`, `pauseHeating`, `sessionProfiling`, `adaptiveExpManagement` (FlexBattery), `responsiveDrawProfile` (FlexPuff), `vapeCloudSize`, `engineJoule`.

Quindi il significato dei registri non è nel JavaScript: si ricava solo dal traffico.

Il backend (`api.uam.iot.iqos.com`, comandi su MQTT via AWS IoT) conserva anche una copia decodificata dello stato del dispositivo, con questi nomi:

- `ledIntensity.intensity`: `DAY_MODE` (100), `NIGHT_MODE` (30); il codice conosce anche `STEALTH_MODE`, non offerto per la ILUMA i ONE;
- `uiHeatingVibration`: `preHeatVibration`, `heatingVibration`, `nearEndHeatVibration`, `heatingEndVibration`, `endChargeVibration`. Sono cinque, come le voci della tabella eventi (`0C 0E 0D 0F 0B`), quindi la tabella è probabilmente questa impostazione e `0x0B` è la fine della ricarica;
- `extHapticProfile.hapticPattern` (altri modelli): `ALLEGRO`, `VIVALDI`, `BUBBLY`, `SIREN`, `CRESCENDO`, `DISABLED`;
- `batteryInfo`: carica 100, temperatura 29, `batteryVoltage` 2124: coincide con il registro `0x181` letto nello stesso momento;
- `associatedDevices.engine`: `DEV_TYPE_P1V41J_ENGINE`, firmware 102.6.0. La rete `c9` è quindi il **modulo di riscaldamento**: non va mai scritta.

### Prova: modalità luci nascosta tramite il backend

Il 14 ottobre 2026 è stata inviata al backend UAM, con la funzione della WebApp `updateUamSettings`, la richiesta `{"settingName":"ledIntensity","newValue":{"intensity":"STEALTH_MODE"}}`, non offerta per la ILUMA i ONE. Le scritture verso il dispositivo erano bloccate nel browser.

- `POST /asset/{id}/device/actions/updateSetting` → `200` con un `requestId`;
- nessun comando è arrivato alla IQOS; la luminosità riletta via USB è rimasta 100;
- `GET /asset/{id}/device/request-status/{requestId}` → `status: FAILED` dopo 1 secondo, `errorCode: CM_ASYNC_REQUEST_FAILED`, «Issue when communicating with CM», `outerErrorMessage: INTERNAL_SERVER_ERROR`, `request.value: run-command`.

Interpretazione (non verificata): il componente del backend che traduce le impostazioni in comandi per il dispositivo non ha una codifica di `STEALTH_MODE` per questo modello. Le modalità degli altri modelli non si ottengono passando dal server.

Nota sul codice della WebApp: `checkUamRequestStatus` restituisce `{status: "PENDING"}` per qualunque risposta che non sia `SUCCESS`, `FAILED` o `CANCELED`, anche quando la richiesta non è partita. Per leggere lo stato vero bisogna chiamare l'endpoint con il client UAM (modulo 29063) e con l'`assetId` presente, cioè a dispositivo collegato.

I quattro byte per evento nella tabella potrebbero quindi essere schemi di **vibrazione**, non animazioni LED: non è verificato.

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
| `0x0B` | probabilmente fine ricarica (`endChargeVibration`), riscritto sempre uguale |

- `vib`: `0x1D` vibrazione attiva, `0x01` spenta.
- `p1..p4`: diversi per evento e mai cambiati dalla WebApp (`13 14 15 16`, `04 01 01 01`, `02 02 02 02`, `07 01 01 01`). Schema di vibrazione o animazione LED dell'evento: **non verificato** (vedi sopra).

In scrittura la voce è preceduta da un byte di controllo e perde l'ultimo zero:

```
payload = [chk] + voce[0:13]
chk     = CRC-8(poly 0x07, init 0x7B) su voce[0:12]
```

La WebApp riscrive sempre tutte e cinque le voci (`0C 0E 0D 0F 0B`), poi conferma con una scrittura da 4 byte `00 ff ff 00` sullo stesso registro, e infine le rilegge.

## Frame estesi

Durante la sincronizzazione la WebApp usa anche un secondo formato, riconoscibile dal bit 4 di `b1`:

```
[len] [net] [flags] [n] [payload n byte] [crc16 LE]
```

- `flags`: bit 7-6 operazione come sopra (`0x10` lettura, `0x50` scrittura, `0x90` risposta, `0xD0` conferma);
- `n`: lunghezza del payload; i primi 2 byte del payload identificano il comando;
- `crc16`: polinomio `0x755B`, init `0x0000`, non riflesso, su `flags` … fine payload, little-endian. Verificato su 17 frame.

Le risposte più lunghe di un report arrivano segmentate sul report `0x40`.

Comandi estesi visti (tutti in lettura, tranne l'orologio):

| Comando | Contenuto |
|---|---|
| `00 04` | orologio: `da 07 01 01` (epoca 2010-01-01) + secondi dall'epoca, u32 LE, ora locale |
| `00 04` in scrittura | la WebApp imposta l'orologio all'ora corrente |
| `01 01` | contatori d'uso (34 byte) |
| `00 00`, `00 01`, `00 02`, `01 00`, `02 00`, `00 06` | tabelle di configurazione, non decodificate |

## Altri registri letti durante la sincronizzazione

| Rete | `S` | Risposta | Interpretazione |
|---|---|---|---|
| `c0` | `0x00C` | 14 byte ASCII | numero di serie |
| `c0` | `0x001` | 14 byte | il «ping» della WebApp; probabilmente versioni hardware/firmware |
| `c0` | `0x181` | `4c 08 64 1d` | **ipotesi**: tensione batteria in unità da 2 mV (4248 mV), carica 100 %, temperatura 29 °C. Una seconda lettura dava `4b 08`, quindi il primo valore varia |
| `c0` | `0x003` | `da 07 01 01` | epoca dell'orologio |
| `c0` | `0x004` | u32 | orologio, secondi dal 2010-01-01 |
| `c0` | `0x084` | `07 06 00 00` | sconosciuto |
| `c9` | `0x009` + chiave | 14 byte per voce | **registro delle sessioni**: la WebApp legge le chiavi da `0x000` a `0x121`; le voci piene contengono data e ora della sessione e altri contatori |
| `c9` | `0x089` + chiave `03`, `04` | `.. 01` | due impostazioni attive, non identificate |

Le risposte da rete `c9` hanno `0x08` come byte di rete.

In lettura su chiavi non supportate il dispositivo risponde con il bit 5 di `b1` acceso (`0xA4`, `0xA7`) e payload `02 00 00 00`: probabilmente un codice d'errore.

La cattura della sincronizzazione non è pubblicata perché contiene il numero di serie e l'orario delle sessioni d'uso.

## Cose che non passano dal dispositivo

Il nome del dispositivo («Rinomina») è salvato solo sull'account IQOS: nessun pacchetto USB.

## Non esplorato

Aggiornamento firmware, ripristino e disaccoppiamento non sono stati toccati.
