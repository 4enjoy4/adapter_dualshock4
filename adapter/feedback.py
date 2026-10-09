"""Short, non-blocking DS4 rumble cues. HID access stays on the input thread."""
import zlib


def rumble_report(bluetooth, left=0, right=0):
    """Motor-only reports preserve the lightbar. Bluetooth includes its HID CRC."""
    data = bytearray(78 if bluetooth else 32)
    data[0] = 0x11 if bluetooth else 0x05
    offset = 3 if bluetooth else 1
    if bluetooth:
        data[1] = 0xC4  # HID + CRC, 4 ms input reporting interval.
    data[offset] = 0x01
    data[offset + 3] = max(0, min(255, round(right)))
    data[offset + 4] = max(0, min(255, round(left)))
    if bluetooth:
        data[-4:] = zlib.crc32(b'\xa2' + data[:-4]).to_bytes(4, 'little')
    return bytes(data)


# left motor, right motor, duration, priority
CUES = {
    'key': (0, 145, .030, 1),
    'edit': (0, 165, .045, 1),
    'open': (60, 130, .060, 2),
    'close': (0, 120, .035, 2),
    'shortcut': (105, 145, .065, 2),
    'enter': (180, 110, .100, 3),
    'error': (180, 0, .140, 4),
}


class Feedback:
    def __init__(self, write):
        self.write = write
        self.until = 0.0
        self.priority = 0
        self.active = False
        self.error = ''
        self.failed = False

    def send(self, left, right):
        try:
            self.write(left, right)
            if not self.failed:
                self.error = ''
            return True
        except (OSError, ValueError):
            self.error = 'Vibration unavailable. Desktop input still works; reconnect to retry.'
            self.failed = True
            return False

    def pulse(self, name, now, strength=.55):
        if self.failed or name not in CUES or strength <= 0:
            return
        left, right, duration, priority = CUES[name]
        # Drop overlapping small cues instead of queuing delayed vibrations.
        if self.active and now < self.until and priority <= self.priority:
            return
        self.active = True  # Also attempt a stop if a write only partly succeeds.
        if not self.send(round(left * strength), round(right * strength)):
            self.stop()
            return
        self.until, self.priority = now + duration, priority

    def tick(self, now, allowed=True):
        if self.active and (not allowed or now >= self.until):
            self.stop()

    def stop(self):
        if self.active:
            self.send(0, 0)
        self.active = False
        self.until = 0.0
        self.priority = 0

    def reconnect(self):
        self.active = self.failed = False
        self.until = 0.0
        self.error = ''
