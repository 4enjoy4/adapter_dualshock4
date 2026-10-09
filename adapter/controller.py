"""Read the physical controller in shared mode; never emulate or hide a gamepad."""
from dataclasses import dataclass
import time

SONY = 0x054C
PRODUCTS = {0x05C4, 0x09CC, 0x0BA0}


@dataclass(frozen=True)
class PadState:
    lx: int = 128
    ly: int = 128
    rx: int = 128
    ry: int = 128
    l2: int = 0
    r2: int = 0
    buttons: frozenset = frozenset()
    touch: tuple | None = None  # contact id, x, y
    battery: int | None = None
    charging: bool = False
    transport: str = "USB"

    def neutral(self, deadzone=0.18):
        return (not self.buttons and self.touch is None and self.l2 < 40 and self.r2 < 40
                and all(abs(v - 128) / 128 <= deadzone
                        for v in (self.lx, self.ly, self.rx, self.ry)))


def parse_report(data, bluetooth=False):
    """DS4 report formats: USB 01/64, Bluetooth 01/10 or 11/78."""
    if not data:
        return None
    if data[0] == 0x11 and len(data) >= 78:
        base, transport, extended = 3, "Bluetooth", True
    elif data[0] == 0x01 and len(data) >= 10:
        extended = len(data) >= 64 and not bluetooth
        base, transport = 1, "USB" if extended else "Bluetooth"
    else:
        return None
    d = data[base:]
    buttons = set()
    for bit, name in enumerate(("square", "cross", "circle", "triangle"), 4):
        if d[4] & (1 << bit):
            buttons.add(name)
    hats = (("up",), ("up", "right"), ("right",), ("right", "down"),
            ("down",), ("down", "left"), ("left",), ("left", "up"))
    hat = d[4] & 15
    if hat < 8:
        buttons.update(hats[hat])
    for bit, name in enumerate(("l1", "r1", "l2", "r2", "share", "options", "l3", "r3")):
        if d[5] & (1 << bit):
            buttons.add(name)
    if d[6] & 1:
        buttons.add("ps")
    if d[6] & 2:
        buttons.add("touch_click")
    touch = None
    battery, charging = None, False
    if extended:
        status = d[29]
        charging = bool(status & 0x10)
        battery = min(100, ((status & 15) + (0 if charging else 1)) * 10)
        # The first touch sample is the latest sample; later slots contain history.
        if d[32] > 0 and len(d) >= 42:
            for start in (34, 38):
                contact, xlo, xy, yhi = d[start:start + 4]
                if not contact & 0x80:
                    x, y = xlo | ((xy & 15) << 8), (xy >> 4) | (yhi << 4)
                    if x < 1920 and y < 942:
                        touch = (contact & 127, x, y)
                        break
    return PadState(*d[:4], d[7], d[8], frozenset(buttons), touch,
                    battery, charging, transport)


class Controller:
    def __init__(self):
        self.device = None
        self.name = "DualShock 4"
        self.last_report = 0.0
        self.product = None
        self.bluetooth = False

    def connect(self):
        import hid
        failures = []
        candidates = [d for d in hid.enumerate(SONY, 0)
                      if d['product_id'] in PRODUCTS and d.get('usage_page') == 1
                      and d.get('usage') in (4, 5)]
        for info in candidates:
            dev = hid.device()
            try:
                dev.open_path(info['path'])
                dev.set_nonblocking(True)
                # Reading calibration enables full Bluetooth input (touchpad/battery).
                # This sends no output report and does not change LEDs or vibration.
                self.bluetooth = (info.get('bus_type') == 2 or b"bluetooth" in info['path'].lower()
                                  or b"00001124" in info['path'].lower())
                if self.bluetooth:
                    try:
                        dev.get_feature_report(0x02, 37)
                    except OSError:
                        pass  # Minimal reports still support sticks and buttons.
                self.device = dev
                self.name = info.get('product_string') or "DualShock 4"
                self.product = info['product_id']
                self.last_report = time.monotonic()
                return True
            except OSError as exc:
                failures.append(str(exc))
                dev.close()
        if failures:
            raise OSError("Controller is busy or hidden by another mapper. " + failures[0])
        return False

    def read(self):
        data = self.device.read(78 if self.bluetooth else 64)
        state = parse_report(data, self.bluetooth)
        if state:
            self.last_report = time.monotonic()
        return state, bool(data)

    def close(self):
        if self.device is not None:
            self.device.close()
            self.device = None
