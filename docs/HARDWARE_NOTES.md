# Hardware notes

Results from one radiator: Acova Atoll TSL-050-050-TF, firmware 2.97, on Home Assistant 2026.11 beta through BlueZ. Other radiators may differ.

## Verified

- Reading all exposed values, and reconnecting after bonding without the button.
- Selecting comfort, eco, frost protection, Auto and pilot wire with single writes.
- Returning from frost protection over Bluetooth, with no button press.
- Setting the comfort temperature. Set to 20 °C with the dial at 23, the heating light cleared.
- Eco is comfort minus 3.5 °C, capped at 19 °C: comfort 20 gave 16.5, comfort 24 gave 19.
- The Auto comfort and eco target sensors showed the expected values in the weekly program.
- Turning open-window detection off and on, confirmed by reading the status register
  back. The radiator's own settings display was not checked, and detection itself
  was not triggered.
- After the server was bonded, the phone app no longer had access: the radiator asked
  it to pair again, with light 2 flashing fast and a prompt to press 2H. Cancelling
  left the server's bond working. The radiator may keep only one bond, but that is
  unproven.
- A schedule written from a Schedule helper for one day, including the read-back.
- Turning the radiator off and on with button 1: it is unreachable while off, then
  comes back in its manual mode, which reads as mode 9 (pilot wire). Selecting the
  weekly program from Home Assistant returned it to app mode, and the schedule resumed.
- The radiator running that schedule in Auto: comfort from 07:00 and back to eco after
  09:00, from the clock the integration set.

## Not yet verified

- A schedule over a full week, and days with several blocks.
- Pairing through the integration's setup flow from an unpaired state.
- Whether pairing the phone again would remove the server's bond.
- Bluetooth proxies and other adapters.
- Any other radiator model.

## The dial

| Mode | Effect of the dial |
| --- | --- |
| Comfort, eco, frost protection, Auto | None, including after 2 minutes |
| Pilot wire | Sets the temperature |

In pilot wire, dial mark 19 read 21.5 to 22 °C, and mark 23 read 26.5 °C. Comfort keeps its own value across a period in pilot wire.

## Lights

The main light's colours differed from the manual's table on the tested radiator:

| Mode | Main light seen | Manual |
| --- | --- | --- |
| Comfort | Red | Green |
| Eco | Green | Orange |
| Frost protection | Orange | Not listed |

The rhythm was three blinks, then steady for about two seconds. The second light was red while heating and green once the temperature was reached.

## Reading the temperature

Register 116/5 returns the temperature in effect, not always the comfort setting. Eco showed 16.5 °C with comfort at 20 °C, and frost protection showed 7 °C. On entering the weekly program it kept the previous mode's value, showing 7 °C after frost protection and 16.5 °C after eco, so the integration hides it in that mode.

Writing a temperature outside comfort is not useful. A write in pilot wire reported a different value on read-back, and it seems to be stored for comfort: a value written that way appeared when comfort was next selected. The integration allows writes only in comfort.

## Bluetooth adapter freezes

The test server's built-in Realtek RTL8852BU (USB ID `0bda:b85b`, firmware `0x0474842d`) froze several times a day, and did so before this integration was installed. The kernel log shows:

```text
Bluetooth: hci0: command 0x2042 tx timeout
Bluetooth: hci0: Unable to disable scanning: -110
Bluetooth: hci0: Resetting usb device.
```

Opcode `0x2042` is LE Set Extended Scan Enable. The kernel resets the chip within seconds, but it usually returns as `hci1`. Home Assistant then keeps resetting it until it returns under the expected name, which took about 5 minutes. In one case it stayed stuck for over an hour until Home Assistant was restarted.

Connecting also stops scanning, so connections may trigger freezes. That is unproven, but it is one reason the integration does not poll. Schedules stored on the radiator are unaffected, while commands sent during a freeze fail with an error.
