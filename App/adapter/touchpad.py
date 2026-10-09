"""Recognize two light taps without treating swipes or presses as clicks."""


class DoubleTap:
    MIN_TAP = .025
    MAX_TAP = .28
    MIN_GAP = .04
    MAX_GAP = .35
    MOVE_LIMIT = 30
    PAIR_DISTANCE = 90

    def __init__(self):
        self.reset()

    def reset(self, ignore_until_up=False):
        self.contact = self.first = None
        self.started = 0.0
        self.ignore_until_up = ignore_until_up

    @staticmethod
    def near(a, b, radius):
        return (a[1]-b[1])**2 + (a[2]-b[2])**2 <= radius**2

    def step(self, touch, now, blocked=False, valid=True):
        # Missing touch samples do not mean the finger was lifted.
        if not valid:
            self.reset(ignore_until_up=True)
            return False
        if blocked:
            self.reset(ignore_until_up=touch is not None)
            return False
        if self.ignore_until_up:
            if touch is None:
                self.reset()
            return False
        if touch is not None:
            if self.contact is None:
                self.contact, self.started = touch, now
                if self.first and (not self.MIN_GAP <= now-self.first[0] <= self.MAX_GAP
                                   or not self.near(touch, self.first[1], self.PAIR_DISTANCE)):
                    self.first = None
            if (touch[0] != self.contact[0] or now-self.started > self.MAX_TAP
                    or not self.near(touch, self.contact, self.MOVE_LIMIT)):
                self.reset(ignore_until_up=True)
            return False
        if self.contact is None:
            if self.first and now-self.first[0] > self.MAX_GAP:
                self.first = None
            return False
        contact, self.contact = self.contact, None
        if not self.MIN_TAP <= now-self.started <= self.MAX_TAP:
            self.first = None
            return False
        if self.first:
            self.first = None
            return True
        self.first = (now, contact)
        return False
