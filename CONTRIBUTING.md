# Contributing

Reports from other radiators are the most useful contribution at this stage.

## Reporting a radiator

Please open an issue with:

- The model, and the firmware from the device page
- Your Home Assistant version and Bluetooth adapter, or proxy
- What worked and what didn't
- The output of `probe.py`, with your Bluetooth address removed

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

The tests use a simulated radiator in `tests/fake_radiator.py`, which follows the protocol as understood. Passing tests do not prove that something works on real hardware, so please test on a radiator where you can, and update [the hardware notes](docs/HARDWARE_NOTES.md).

## Guidelines

- Keep `protocol.py` free of Home Assistant imports, as `probe.py` depends on that.
- Don't name a file in `custom_components/acova` after a Python standard library module other than the platform files already there. `probe.py` removes that folder from its import path because of `select.py`.
- Don't commit code or assets from the official app, or the Acova and Zehnder logos.
- Don't send a command to the radiator that the app doesn't use without testing it. Standby is the example: it cuts Bluetooth until someone presses the radiator's button.
