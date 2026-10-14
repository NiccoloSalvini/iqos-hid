#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["hidapi>=0.14"]
# ///
"""Legge e cambia le impostazioni di una IQOS ILUMA via USB.

Il dispositivo espone un'interfaccia HID con usage page proprietaria (0xFF00).
Le richieste viaggiano sul report 0x3F; il formato e i registri sono descritti
in PROTOCOL.md. Le scritture sono limitate ai registri catturati dalla WebApp
ufficiale: non c'e' un comando per scrivere registri arbitrari.
"""

import argparse
import json
import sys
import time
from datetime import datetime

import hid

VENDOR_ID = 0x2759  # Philip Morris Products S.A.
KNOWN_PRODUCTS = {0x0003: "IQOS ILUMA i ONE"}
REPORT = 0x3F
NET = 0xC0

OP_READ, OP_WRITE, OP_READ_RESP, OP_WRITE_ACK = 0, 1, 2, 3
LEN_CODES = {0: 0, 4: 1, 14: 2, 24: 3}

# Registri noti. S e' l'indirizzo a 10 bit: byte2 << 2 | 2 bit bassi di byte1.
REG_BRIGHTNESS = 0x24 << 2      # u32, percentuale (WebApp: 30 bassa, 100 alta)
REG_LOCK = 0x04 << 2            # u32, 0 sbloccato, 0x0000ff02 bloccato
REG_AUTOSTART = 0x24 << 2 | 3   # tabella: chiave 0x01, valore nel byte 1
REG_EVENTS = 0x04 << 2 | 3      # tabella degli eventi (vibrazione e LED)

LOCKED = bytes([0x02, 0xFF, 0x00, 0x00])
EVENTS = {0x0C: "riscaldamento", 0x0E: "pronto", 0x0D: "quasi-finito", 0x0F: "finito"}
EVENT_TABLE_KEYS = [0x0C, 0x0E, 0x0D, 0x0F, 0x0B]
VIBRATION_ON, VIBRATION_OFF = 0x1D, 0x01


def crc8(data, init=0):
    c = init
    for x in data:
        c ^= x
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def frame(op, reg, payload=b""):
    """Costruisce i 63 byte del report 0x3F."""
    b1 = op << 6 | LEN_CODES[len(payload)] << 2 | (reg & 3)
    body = bytes([b1, reg >> 2]) + bytes(payload)
    msg = bytes([NET]) + body + bytes([crc8(body)])
    return (bytes([len(msg)]) + msg).ljust(63, b"\x00")


def parse(data):
    """Restituisce (op, reg, payload) da un report in ingresso, o None."""
    if len(data) < 5 or data[1] != NET:
        return None
    n = data[0]
    b1, b2 = data[2], data[3]
    payload = bytes(data[4 : n])
    if crc8(data[2 : n]) != data[n]:
        return None
    return b1 >> 6, b2 << 2 | (b1 & 3), payload


class Iqos:
    def __init__(self, info):
        self.dev = hid.device()
        self.dev.open_path(info["path"])
        self.info = info

    def close(self):
        self.dev.close()

    def _request(self, op, reg, payload=b"", expect=None, timeout=0.5):
        self.dev.write(bytes([REPORT]) + frame(op, reg, payload))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.dev.read(64, 100)
            if not data:
                continue
            got = parse(bytes(data[1:]) if data[0] == REPORT else bytes(data))
            if got and got[0] == expect and got[1] == reg:
                return got[2]
        raise TimeoutError(f"nessuna risposta dal registro 0x{reg:03x}")

    def read(self, reg, key=b""):
        return self._request(OP_READ, reg, key, OP_READ_RESP)

    def write(self, reg, payload):
        self._request(OP_WRITE, reg, payload, OP_WRITE_ACK)

    def read_u32(self, reg):
        return int.from_bytes(self.read(reg)[:4], "little")

    def write_u32(self, reg, value):
        self.write(reg, value.to_bytes(4, "little"))

    def event(self, key):
        return self.read(REG_EVENTS, bytes([key, 0, 0, 0]))

    def write_events(self, entries):
        """Riscrive la tabella degli eventi come fa la WebApp: tutte le voci, poi conferma."""
        for key in EVENT_TABLE_KEYS:
            entry = entries[key][:13]
            self.write(REG_EVENTS, bytes([crc8(entry[:12], 0x7B)]) + entry)
        self.write(REG_EVENTS, bytes([0x00, 0xFF, 0xFF, 0x00]))


def find_devices():
    return [d for d in hid.enumerate(VENDOR_ID) if d["usage_page"] in (0xFF00, 0)]


def mask(serial: str) -> str:
    return serial[:3] + "…" + serial[-2:] if serial and len(serial) > 5 else serial


def open_device():
    devices = find_devices()
    if not devices:
        sys.exit("Nessuna IQOS trovata. Usa un cavo dati, non solo di ricarica.")
    return Iqos(devices[0])


def cmd_list(args):
    devices = find_devices()
    if not devices:
        print("Nessuna IQOS trovata. Usa un cavo dati, non solo di ricarica.")
        return 1
    for d in devices:
        serial = d["serial_number"] if args.show_serial else mask(d["serial_number"])
        print(
            f"{d['product_string'] or KNOWN_PRODUCTS.get(d['product_id'], '?')}"
            f"  VID=0x{d['vendor_id']:04x} PID=0x{d['product_id']:04x}"
            f"  release=0x{d['release_number']:04x}"
            f"  usage_page=0x{d['usage_page']:04x} usage=0x{d['usage']:02x}"
            f"  serial={serial}"
        )
    return 0


def cmd_status(args):
    iq = open_device()
    try:
        print(f"luminosità      {iq.read_u32(REG_BRIGHTNESS)}%")
        print(f"blocco          {'sì' if iq.read(REG_LOCK)[:4] == LOCKED else 'no'}")
        print(f"avvio automatico {'on' if iq.read(REG_AUTOSTART, bytes([1, 0, 0, 0]))[1] else 'off'}")
        for key, name in EVENTS.items():
            e = iq.event(key)
            vib = {VIBRATION_ON: "on", VIBRATION_OFF: "off"}.get(e[11], f"0x{e[11]:02x}")
            print(f"vibrazione {name:<13} {vib:<4} LED {e[5:9].hex(' ')}")
    finally:
        iq.close()
    return 0


def cmd_set(args):
    iq = open_device()
    try:
        if args.what == "brightness":
            value = int(args.value)
            if not 1 <= value <= 100:
                sys.exit("La luminosità va da 1 a 100.")
            iq.write_u32(REG_BRIGHTNESS, value)
            print(f"luminosità → {iq.read_u32(REG_BRIGHTNESS)}%")
        elif args.what == "autostart":
            on = args.value == "on"
            iq.write(REG_AUTOSTART, bytes([1, int(on), 0, 0]))
            print(f"avvio automatico → {'on' if iq.read(REG_AUTOSTART, bytes([1, 0, 0, 0]))[1] else 'off'}")
        elif args.what == "lock":
            iq.write(REG_LOCK, LOCKED if args.value == "on" else bytes(4))
            print(f"blocco → {'sì' if iq.read(REG_LOCK)[:4] == LOCKED else 'no'}")
        elif args.what == "vibration":
            event, state = args.value.split("=")
            key = {v: k for k, v in EVENTS.items()}.get(event)
            if key is None or state not in ("on", "off"):
                sys.exit(f"Usa: set vibration <{'|'.join(EVENTS.values())}>=on|off")
            entries = {k: bytearray(iq.event(k)) for k in EVENT_TABLE_KEYS}
            entries[key][11] = VIBRATION_ON if state == "on" else VIBRATION_OFF
            iq.write_events(entries)
            print(f"vibrazione {event} → {'on' if iq.event(key)[11] == VIBRATION_ON else 'off'}")
    finally:
        iq.close()
    return 0


def cmd_listen(args):
    devices = find_devices()
    if not devices:
        print("Nessuna IQOS trovata.", file=sys.stderr)
        return 1
    info = devices[0]
    dev = hid.device()
    dev.open_path(info["path"])
    print(f"In ascolto su {info['product_string']} (Ctrl+C per uscire)", file=sys.stderr)

    log = open(args.log, "a") if args.log else None
    deadline = time.monotonic() + args.seconds if args.seconds else None
    count = 0
    try:
        while deadline is None or time.monotonic() < deadline:
            data = dev.read(64, 250)
            if not data:
                continue
            count += 1
            now = datetime.now().isoformat(timespec="milliseconds")
            report_id, payload = data[0], bytes(data[1:])
            shown = payload.rstrip(b"\x00") if not args.full else payload
            print(f"{now}  id=0x{report_id:02x}  len={len(payload)}  {shown.hex(' ')}")
            if log:
                log.write(json.dumps({"t": now, "report_id": report_id, "data": payload.hex()}) + "\n")
                log.flush()
    except KeyboardInterrupt:
        pass
    finally:
        dev.close()
        if log:
            log.close()
    print(f"{count} report ricevuti.", file=sys.stderr)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="elenca le IQOS collegate")
    pl.add_argument("--show-serial", action="store_true", help="mostra il seriale completo")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("status", help="legge le impostazioni")
    ps.set_defaults(func=cmd_status)

    pw = sub.add_parser("set", help="cambia un'impostazione")
    pw.add_argument("what", choices=["brightness", "autostart", "lock", "vibration"])
    pw.add_argument("value", help="1-100 | on/off | evento=on/off")
    pw.set_defaults(func=cmd_set)

    pr = sub.add_parser("listen", help="stampa i report in arrivo, senza mai scrivere")
    pr.add_argument("--seconds", type=float, help="ferma dopo N secondi")
    pr.add_argument("--log", help="salva i report in un file JSON Lines")
    pr.add_argument("--full", action="store_true", help="non tagliare gli zeri finali")
    pr.set_defaults(func=cmd_listen)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
