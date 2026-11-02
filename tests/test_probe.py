"""Runs probe.py as a script would, against the fake radiator."""

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.acova import protocol
from fake_radiator import FakeRadiator

PROBE = Path(protocol.__file__).with_name("probe.py")


def test_probe_runs_as_a_script():
    """Its folder must not shadow standard modules such as select."""
    result = subprocess.run(
        [sys.executable, str(PROBE), "--help"], capture_output=True, text=True, cwd="/"
    )
    assert result.returncode == 0, result.stderr


async def test_probe_explore_only_reads(capsys):
    spec = importlib.util.spec_from_file_location("acova_probe", PROBE)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    fake = FakeRadiator()
    fake.services = [
        SimpleNamespace(
            uuid="svc",
            characteristics=[SimpleNamespace(uuid="chr", properties=["read"])],
        )
    ]
    for register in probe.explore_registers():
        fake.registers.setdefault(tuple(register), [0])
    device = MagicMock(address="AA", name="x")
    device.name = "TEMPO 3"
    adv = SimpleNamespace(local_name="TEMPO 3")
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=fake)
    client.__aexit__ = AsyncMock(return_value=False)

    class Scanner:
        def __init__(self, callback):
            self.callback = callback

        async def start(self):
            self.callback(device, adv)

        async def stop(self):  # what BlueZ did when the adapter dropped out
            raise probe.BleakError("No discovery started")

    with patch.object(probe, "BleakScanner", Scanner), \
            patch.object(probe, "BleakClient", return_value=client):
        await probe.main(argparse.Namespace(explore=True))
    out = capsys.readouterr().out
    assert "116/5: 2a [42]" in out
    assert "RadiatorState(mode=4" in out
    assert fake.commits == []
