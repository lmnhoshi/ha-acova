"""Simulates the radiator side of the protocol as read from the app."""

from custom_components.acova.protocol import CHAR_COMMAND, CHAR_DATA


class FakeRadiator:
    is_connected = True

    def __init__(self):
        self.registers = {
            (100, 1): [55], (100, 2): [2],
            (113, 1): [1], (113, 2): [0],
            (116, 3): [4], (116, 4): [35], (116, 5): [42], (116, 6): [0xEC],
            (117, 3): list(range(1, 21)),
        }
        for data_id in range(4, 10):
            self.registers[(117, data_id)] = [3] + [0] * 19
        self.data = bytes(30)
        self.staged = None
        self.callback = None
        self.commits = []
        self.reject = set()
        self.echo_delay = 0
        self.silent = set()
        self.paired = False
        self.disconnected = False
        self.pair_error = None
        self.reads_before_pair = 0

    async def pair(self):
        if self.pair_error:
            raise self.pair_error
        assert self.reads_before_pair > 0, "must pair after the button press"
        self.paired = True

    async def disconnect(self):
        self.disconnected = True

    async def start_notify(self, char, callback):
        assert char == CHAR_DATA
        self.callback = callback

    async def read_gatt_char(self, char):
        assert char == CHAR_DATA
        if self.echo_delay:
            self.echo_delay -= 1
            return bytes(30)
        return self.data

    async def write_gatt_char(self, char, data, response=None):
        assert response is True
        if char == CHAR_DATA:
            assert len(data) == 30
            self.staged = data
            self.data = data
        elif char == CHAR_COMMAND:
            assert len(data) == 3
            op, obj, did = data
            if op == 0:
                if (obj, did) in self.silent:
                    return
                self.reads_before_pair += 1
                value = self.registers[(obj, did)]
                frame = bytes((obj, did, len(value), *value))
                self.data = frame
                self.callback(None, bytearray(frame[:20]))  # 20-byte notification
            else:
                assert op == 1 and self.staged[:2] == bytes((obj, did))
                length = self.staged[2]
                self.commits.append((obj, did, list(self.staged[3:3 + length])))
                if (obj, did) not in self.reject:
                    self.registers[(obj, did)] = list(self.staged[3:3 + length])
                self.data = bytes(30)
        else:
            raise AssertionError(char)
