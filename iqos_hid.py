#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["hidapi>=0.14"]
# ///
"""Ascolto passivo del canale HID USB di una IQOS ILUMA.

Il dispositivo espone un'interfaccia HID con usage page proprietaria (0xFF00)
e due report da 63 byte (ID 0x3F e 0x40) in ingresso e in uscita. Questo
script apre il dispositivo e stampa SOLO quello che arriva: non scrive mai.
"""

import argparse
import json
import sys
import time
from datetime import datetime

import hid

VENDOR_ID = 0x2759  # Philip Morris Products S.A.
KNOWN_PRODUCTS = {0x0003: "IQOS ILUMA i ONE"}


def find_devices():
    return [d for d in hid.enumerate(VENDOR_ID) if d["usage_page"] == 0xFF00 or d["usage_page"] == 0]


def mask(serial: str) -> str:
    return serial[:3] + "…" + serial[-2:] if serial and len(serial) > 5 else serial


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

    pr = sub.add_parser("listen", help="stampa i report in arrivo, senza mai scrivere")
    pr.add_argument("--seconds", type=float, help="ferma dopo N secondi")
    pr.add_argument("--log", help="salva i report in un file JSON Lines")
    pr.add_argument("--full", action="store_true", help="non tagliare gli zeri finali")
    pr.set_defaults(func=cmd_listen)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
