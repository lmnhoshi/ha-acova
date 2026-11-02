#!/usr/bin/env python3
"""Read-only hardware check. Run inside the Home Assistant container.

Changes no radiator settings, but tries to bond it with the Bluetooth adapter.

  python3 /config/custom_components/acova/probe.py            find and read
  python3 /config/custom_components/acova/probe.py --explore  also dump unknown registers
"""

import importlib.util
from pathlib import Path
import sys

# This folder has select.py and number.py, which would replace Python's own
# select module, so it must leave the path before anything else is imported.
HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]

import argparse  # noqa: E402
import asyncio  # noqa: E402

from bleak import BleakClient, BleakScanner  # noqa: E402
from bleak.exc import BleakError  # noqa: E402

_spec = importlib.util.spec_from_file_location("acova_protocol", HERE / "protocol.py")
protocol = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = protocol
_spec.loader.exec_module(protocol)
DEVICE_NAME_MARKER = protocol.DEVICE_NAME_MARKER
AcovaSession = protocol.AcovaSession
Register = protocol.Register

PAIR_WINDOW = 45
SCAN_SECONDS = 20


def explore_registers():
    """Yield the app's objects in depth, then a light sweep of unused objects."""
    known = (100, 113, 115, 116, 117)
    for object_id in known:
        for data_id in range(1, 31):
            yield Register(object_id, data_id)
    for object_id in range(90, 131):
        if object_id not in known:
            for data_id in range(1, 4):
                yield Register(object_id, data_id)


async def wait_for_state(session: AcovaSession):
    """Retry reads until the radiator's button has been pressed."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PAIR_WINDOW
    while True:
        try:
            return await session.read_state()
        except Exception as err:
            if loop.time() > deadline:
                raise
            print(f"  not ready ({type(err).__name__}: {err}), retrying")
            await asyncio.sleep(2)


async def scan() -> tuple[list, set]:
    """Scan until a radiator appears, keeping results if the adapter drops out."""
    radiators: list = []
    names: set = set()

    def on_advert(device, adv) -> None:
        name = adv.local_name or device.name or ""
        if name:
            names.add(name)
        if DEVICE_NAME_MARKER in name:
            radiators.append(device)

    scanner = BleakScanner(on_advert)
    try:
        await scanner.start()
    except BleakError as err:
        raise SystemExit(f"Bluetooth adapter is unavailable, retry shortly: {err}") from err
    for _ in range(SCAN_SECONDS):
        await asyncio.sleep(1)
        if radiators:
            break
    try:
        await scanner.stop()
    except BleakError as err:
        print(f"Scan was interrupted, the adapter probably dropped out: {err}")
    return radiators, names


async def main(args) -> None:
    print(f"Scanning up to {SCAN_SECONDS} s for '{DEVICE_NAME_MARKER}'...")
    radiators, names = await scan()
    if not radiators:
        raise SystemExit(f"No radiator found. Named devices seen: {sorted(names)}")
    device = radiators[0]
    print(f"Found {device.name} {device.address}, connecting...")
    print(">>> When light 2 flashes green, press the 2H boost button (3) <<<")

    async with BleakClient(device, timeout=30) as client:
        for service in client.services:
            print(f"service {service.uuid}")
            for char in service.characteristics:
                print(f"  char {char.uuid} {char.properties}")
        session = AcovaSession(client)
        await session.start()
        print(await wait_for_state(session))
        try:
            await asyncio.wait_for(client.pair(), PAIR_WINDOW)
            print("Bluetooth bond is in place")
        except Exception as err:
            print(f"Bonding failed, the button will be needed every time: {err!r}")
        if args.explore:
            for register in explore_registers():
                name = f"{register.object_id}/{register.data_id}"
                try:
                    value = await session.read(register, timeout=2)
                    print(f"{name}: {value.hex()} {list(value)}", flush=True)
                except TimeoutError:
                    pass  # unknown registers are the common case
                except Exception as err:
                    print(f"{name}: {type(err).__name__}", flush=True)
    print("Finished: nothing was written to the radiator.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explore", action="store_true")
    asyncio.run(main(parser.parse_args()))
