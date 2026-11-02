# Bluetooth protocol

Worked out by studying the ACOVA Control 3.4.1 Android app, then checked against a radiator running firmware 2.97. This is not an official specification. The repository contains no code from the app.

## Discovery and pairing

The radiator advertises a name containing `TEMPO 3`. The app lists only devices with that name.

The app adds no encryption or login of its own. Access relies on the 2H button and standard Bluetooth pairing:

- Without a bond, the radiator ignores requests until the 2H button is pressed, and this applies to each connection. Requests in the meantime time out.
- With a bond, it answers immediately.
- On the tested radiator, pairing failed with `AuthenticationFailed` when requested straight after connecting, with no agent registered. It succeeded from `bluetoothctl` after the button press with a `NoInputNoOutput` agent. Which of those two differences mattered is unknown.

## GATT layout

| Name | Service | Characteristic | Properties |
| --- | --- | --- | --- |
| COMMAND | `03366e80-cf3a-11e1-9ab4-0002a5d5c51b` | `350a1b80-cf4b-11e1-ac36-0002a5d5c51b` | write |
| DATA | `03366e80-cf3a-11e1-9ab5-0002a5d5c51b` | `350a1b80-cf4b-11e1-ac37-0002a5d5c51b` | read, write, notify |

## Reading a register

1. Subscribe to notifications on DATA.
2. Write `00 <object> <data>` to COMMAND.
3. Receive a notification: `<object> <data> <length> <payload>`.
4. If `length` is above 17, the notification was cut short, so read DATA for the whole frame.

Addresses that don't exist send no reply. The app waits 8 seconds before giving up.

## Writing a register

1. Write a 30-byte frame to DATA: `<object> <data> <length> <payload>`, padded with zeros.
2. Read DATA until it starts with `<object> <data>`.
3. Write `01 <object> <data>` to COMMAND to commit.
4. Read DATA until it starts with `00 00`.

The radiator can accept single register writes. The app itself always sends the window, thermostat, clock and schedule groups together.

## Registers

Addresses are written `object/data`. "Verified" means observed on a real radiator. "From the app" means taken from the app's code only.

| Address | Meaning | Encoding | Status |
| --- | --- | --- | --- |
| 100/1 | Product firmware, minor | byte | Verified |
| 100/2 | Product firmware, major | byte | Verified |
| 100/3 | Bluetooth firmware, low | byte | Reads a value, meaning from the app |
| 100/4 | Bluetooth firmware, high | byte | Reads a value, meaning from the app |
| 113/1 | Window detection status | bit 0: enabled | Verified |
| 113/2 | Window detection control | bit 0: enable, bit 1: disable | Verified: status follows it |
| 115/1 | Calendar status | byte | Reads a value, meaning from the app |
| 115/2 | Calendar control | bit 0: lock, bit 2: apply clock | Verified: the schedule ran on time |
| 115/3 | Weekday | 1 is Monday, 7 is Sunday | Write accepted |
| 115/7 | Hour | byte | Write accepted |
| 115/8 | Minute | byte | Write accepted |
| 115/9 | Second | byte | Write accepted |
| 116/3 | Mode | see below | Verified |
| 116/4 | Eco temperature | half degrees | Reads a value, exact behaviour unclear |
| 116/5 | Reading: temperature in effect. Writing: comfort temperature | half degrees | Verified |
| 116/6 | Calibration offset | signed byte, tenths of a degree | Read only so far |
| 117/1 | Schedule status | byte | From the app |
| 117/3 to 117/9 | Monday to Sunday schedule | 20 bytes, see below | Verified for one day with one block |

Calendar registers read as two bytes on the tested radiator, with the value in the first. The app writes one byte.

### Modes

| Value | Mode | Notes |
| --- | --- | --- |
| 1 | Standby | Cuts Bluetooth until the physical button is pressed. Not offered by the app's interface |
| 2 | Frost protection | Fixed at 7 °C |
| 3 | Eco | Comfort minus 3.5 °C, at most 19 °C |
| 4 | Comfort | |
| 8 | User program ("PU") | Runs the stored schedule |
| 9 | Auto (pilot wire) | The dial sets the temperature. Also what the radiator reports in manual mode, after button 1 turns it off and on |

### Setting the clock

The app writes these in order:

1. 115/2 = `1`
2. 115/7, 115/8, 115/9: hour, minute, second
3. 115/3: weekday
4. 115/2 = `5`

### Schedule format

Each day holds 20 bytes:

```text
<mode at 00:00> 00 <mode> <hour*4> <mode> <hour*4> ... zeros
```

Mode is `04` for comfort or `03` for eco. Each pair marks a change, so a day holds up to 9 changes. Comfort from 06:00 to 08:00 and from 18:00 to 22:00 is:

```text
03 00 04 18 03 20 04 48 03 58 00 00 00 00 00 00 00 00 00 00
```

A radiator that was never programmed was read as all zeros.
