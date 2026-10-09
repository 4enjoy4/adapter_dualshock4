"""Directional repeat shared by both sticks and the D-pad."""
DIRECTIONS = ('up', 'down', 'left', 'right')


class Navigation:
    def __init__(self):
        self.reset()

    def reset(self):
        self.direction = None
        self.next_at = self.started = 0.0

    def step(self, x, y, now, speed=1.25, buttons=()):
        direction = next((d for d in DIRECTIONS if d in buttons), None)
        x, y = x - 128, y - 128
        if direction is None:
            # Hysteresis prevents noisy sticks alternating between diagonal axes.
            threshold = 42 if self.direction else 55
            if max(abs(x), abs(y)) >= threshold:
                horizontal = abs(x) > abs(y)
                if self.direction and abs(abs(x)-abs(y)) < 18:
                    horizontal = self.direction in ('left', 'right')
                direction = ('right' if x > 0 else 'left') if horizontal else ('down' if y > 0 else 'up')
        if direction != self.direction:
            self.direction = direction
            self.started, self.next_at = now, now + .23/speed
            return direction
        if direction and now >= self.next_at:
            interval = .085 if now-self.started < .7 else .050
            self.next_at = now + interval/speed
            return direction
        return None
