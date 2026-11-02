# Acova Bluetooth Radiator for Home Assistant

Control an Acova towel radiator from Home Assistant over Bluetooth, with no phone and no cloud.

This is an unofficial community project. It is not affiliated with or endorsed by Acova or Zehnder Group. Use it at your own risk: it controls a heating appliance, and it was built by studying how the official app talks to the radiator, not from any published specification.

> [!IMPORTANT]
> **Wait for each action to finish.** Every change, refresh or schedule sync takes **usually 3 to 10 seconds**, sometimes longer, before the screen updates. The integration connects to the radiator, sends the change, waits for the radiator to apply it and reads it back.
>
> Don't click again while you wait. Extra clicks don't speed anything up: they queue behind the first one and each opens a new connection.

## Status

Early release, tested on **one radiator**. See [what has been verified](docs/HARDWARE_NOTES.md).

| Item | Tested with |
| --- | --- |
| Radiator | Acova Atoll, model TSL-050-050-TF, firmware 2.97 |
| Home Assistant | 2026.11 beta on real hardware, 2026.10 in automated tests |
| Bluetooth | The server's built-in adapter through BlueZ |

It should work with radiators that the ACOVA Control app can pair with, which advertise a Bluetooth name containing `TEMPO 3`. Please report results for other models.

## Features

- Set the mode: comfort, eco, frost protection, weekly program or pilot wire
- Set the comfort temperature, 7 to 30 °C in 0.5 °C steps
- Draw a weekly schedule in a Home Assistant Schedule helper and store it on the radiator, which then runs it without the server
- Turn open-window detection on or off

## Requirements

- Home Assistant 2026.10 or newer, with the Bluetooth integration working
- A Bluetooth adapter within range of the radiator
- Physical access to the radiator's 2H boost button for pairing

## Installation

### HACS

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/lmnhoshi/ha-acova` with the type **Integration**.
3. Install **Acova Bluetooth Radiator** and restart Home Assistant.

### Manual

Copy `custom_components/acova` into your Home Assistant `custom_components` folder and restart.

## Setup

1. Close the ACOVA Control app. The radiator may serve only one connection at a time.
2. Switch the radiator on.
3. Accept the discovered radiator under **Settings > Devices & services**, or add **Acova Bluetooth Radiator** there.
4. Submit the form. When light 2 flashes green, press the 2H boost button within 30 seconds.

If setup reports a pairing failure, [bond by hand](#bonding-by-hand) and add the radiator again. Setup through Home Assistant has not yet been tested from an unpaired state.

## Entities

Remember that each action takes several seconds. See the notice at the top.

Names assume a radiator called `TEMPO 3`. Check your own entity IDs after setup.

| Entity | Purpose |
| --- | --- |
| `select.tempo_3_mode` | All five modes in one control |
| `number.tempo_3_temperature` | The temperature in effect, settable in comfort only |
| `climate.tempo_3` | The same controls as a thermostat, as HVAC modes and presets |
| `switch.tempo_3_open_window_detection` | Open-window detection |
| `button.tempo_3_refresh_from_radiator` | Read the radiator now |
| `button.tempo_3_sync_schedule_to_radiator` | Write the Schedule helper to the radiator |
| `sensor.tempo_3_last_read` | When the values on screen were read |
| `sensor.tempo_3_auto_comfort_target` | Comfort temperature used by the weekly program. Blank in other modes |
| `sensor.tempo_3_auto_eco_target` | Eco temperature used by the weekly program. Blank in other modes |

The radiator only reports its comfort setting while in comfort, so the Auto target sensors stay blank until the integration has seen comfort once. They show a remembered value, so a change made with the phone app won't appear until comfort is selected again. Eco is calculated as comfort minus 3.5 °C, limited to 7-19 °C, as the radiator does.

The climate entity always shows two mode controls, because Home Assistant builds that view. If you prefer one, disable the climate entity and use the select and number entities.

## Modes

| Mode | Select option | Climate | Temperature comes from | Set from Home Assistant? | Dial works? |
| --- | --- | --- | --- | --- | --- |
| Comfort | `comfort` | Heat | Home Assistant | Yes | No |
| Eco | `eco` | Heat, preset eco | Comfort minus 3.5 °C, at most 19 °C | No | No |
| Off (frost protection) | `frost_protection` | Off | Fixed at 7 °C | No | No |
| Auto (weekly program) | `program` | Auto | The stored schedule | No | No |
| Pilot wire | `pilot_wire` | Auto, preset pilot wire | The dial | No | Yes |

- **Off is frost protection.** The radiator can still heat if the room nears 7 °C. The real standby mode cuts Bluetooth until someone presses the radiator's button, so this integration never sends it.
- **The app's "Auto" is pilot wire here.** The app's weekly program, "PU", is **Auto (weekly program)** here.
- **The temperature is blank in Auto,** because the radiator's value there can be out of date.
- **Button 1 on the radiator leaves app mode.** After turning it off and on there, it comes back in manual mode, shown here as pilot wire, and the schedule stops. Select **Auto (weekly program)** to resume it. Home Assistant only sees this after a refresh. Use **Off (frost protection)** instead to keep it under Home Assistant's control.
- **The dial is a rough guide in pilot wire.** The tested radiator read about 2.5 to 3.5 °C above the dial's marks.

## Weekly schedule

1. Create a helper under **Settings > Devices & services > Helpers > Create helper > Schedule**.
2. Draw the hours you want in comfort. Everything else becomes eco.
3. Open the integration, choose **Configure**, and select the helper.
4. Press **Sync schedule to radiator**, and set the mode to **Auto (weekly program)**.

Good to know:

- Editing the helper sends nothing until you sync again.
- The radiator works in whole hours, so blocks are widened to every hour they touch: 06:45 to 07:15 becomes 06:00 to 08:00.
- Each day allows 9 changes between comfort and eco, which is usually 4 separate blocks. A day over the limit gives an error and nothing is written.
- Comfort hours use the temperature last set in comfort. To change it, select comfort, set the temperature, then return to Auto.
- Each sync logs the previous schedule as a warning, since the radiator keeps no other copy.

To sync only some days, use the action:

```yaml
action: acova.sync_schedule
data:
  days:
    - monday
```

## Automation example

Set the mode first, because the temperature can only be set in comfort.

```yaml
automation:
  - alias: Towel radiator warm-up
    triggers:
      - trigger: time
        at: "06:30:00"
    actions:
      - action: select.select_option
        target:
          entity_id: select.tempo_3_mode
        data:
          option: comfort
      - action: number.set_value
        target:
          entity_id: number.tempo_3_temperature
        data:
          value: 22
```

Prefer the weekly schedule where you can. It runs on the radiator, so it still works if the server or its Bluetooth adapter is down. An automation does not.

## Limitations

- **No room temperature.** The official app never reads one, and no register for it has been identified.
- **No polling.** Values are read at startup, after each command and when you press refresh. Changes made on the radiator itself appear only after a refresh.
- **The radiator can take a while to reappear after being switched on.** A refresh straight after power-on may report it as out of range.
- **One connection at a time.** Close the phone app while using Home Assistant.
- **Pairing Home Assistant can lock out the phone app.** On the tested radiator, the app then asked to pair again. Cancelling kept Home Assistant working. Pairing the phone again may in turn lock out Home Assistant, which has not been tested.
- **The app can overwrite Home Assistant's settings.** When the app sends settings, it writes its own schedule too.

## Troubleshooting

### Nothing happens after a click

Wait at least 10 seconds before trying again. If an action fails, Home Assistant shows an error, so no error and no change usually means it is still working. A schedule sync takes longer, because it reads and writes each day.

### Bonding by hand

Without a bond, the radiator asks for the 2H button on every connection. On the Home Assistant host, run `bluetoothctl`, then:

```text
agent NoInputNoOutput
default-agent
scan le
scan off                 # once TEMPO 3 has appeared
connect <address>        # press 2H when light 2 flashes green
pair <address>
trust <address>
disconnect <address>
exit
```

### "Could not reach radiator" or "not in Bluetooth range"

Check the radiator is on and the phone app is closed, then try again. If it keeps failing, look for Bluetooth errors in the Home Assistant log and kernel log:

```sh
sudo journalctl -k --since "1 hour ago" | grep -i bluetooth
```

The tested server's Realtek adapter (RTL8852BU, USB ID `0bda:b85b`) freezes now and then, with `command 0x2042 tx timeout`, and this happened before the integration was installed. Home Assistant usually recovers in about 5 minutes. If it keeps logging `has moved to hci0` or `hci1`, restart Home Assistant. A separate USB Bluetooth adapter is the likely lasting fix, though that has not been tested yet.

### "Radiator stayed in mode" or "Radiator kept"

The radiator did not apply the change. Please [open an issue](https://github.com/lmnhoshi/ha-acova/issues) with your model and firmware.

### Read-only check

This reads the radiator without changing its settings, although it does try to bond with the adapter. For Docker installs:

```sh
docker exec -it homeassistant python3 /config/custom_components/acova/probe.py
```

Add `--explore` to list every register that answers, which takes about 15 minutes.

### Debug logs

Use **Enable debug logging** on the integration's page, or add:

```yaml
logger:
  logs:
    custom_components.acova: debug
```

## Removal

Delete the radiator under **Settings > Devices & services**, then remove the integration in HACS or delete its folder, and restart. To remove the bond too, run `bluetoothctl remove <address>` on the host.

## Further reading

- [Bluetooth protocol](docs/PROTOCOL.md)
- [Hardware notes and test results](docs/HARDWARE_NOTES.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE). Acova and Zehnder are trademarks of their respective owners and are used here only to identify compatible products.
