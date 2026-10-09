"""Pure input translation. No Windows calls: pause and release behavior is testable."""
import math

KEYS = {
    "circle": (0x1B,), "square": (0x08,),
    "up": (0x26,), "down": (0x28,), "left": (0x25,), "right": (0x27,),
    "l1": (0x11, 0x10, 0x09), "r1": (0x11, 0x09),
}
REPEAT = {"up", "down", "left", "right", "square"}
SHORTCUTS = {
    'square': (0x11, 0x43), 'triangle': (0x11, 0x56),
    'cross': (0x11, 0x41), 'circle': (0x11, 0x58),
    'l1': (0x11, 0x5A), 'r1': (0x11, 0x59),
    'left': (0x11, 0x10, 0x09), 'right': (0x11, 0x09),
}


def axis(value, deadzone):
    v = (value - 128) / (128 if value <= 128 else 127)
    if abs(v) <= deadzone:
        return 0.0
    return math.copysign(((abs(v) - deadzone) / (1 - deadzone)) ** 1.6, v)


class Engine:
    def __init__(self, sink, toggle_mode, settings, keyboard_active=lambda: False, panel_action=lambda action: None):
        self.sink, self.toggle_mode, self.settings = sink, toggle_mode, settings
        self.previous = frozenset()
        self.active = False
        self.armed = False
        self.last_time = None
        self.mouse = set()
        self.repeats = {}
        self.touch = None
        self.fractions = [0.0, 0.0, 0.0]
        self.chord_start = None
        self.chord_fired = False
        self.options_pending = False
        self.keyboard_active = keyboard_active
        self.panel_action = panel_action
        self.last_keyboard = False
        self.shortcut_latched = False
        self.nav_direction = None
        self.nav_repeat_at = 0.0

    def reset(self):
        self.sink.release_all()
        self.mouse.clear()
        self.repeats.clear()
        self.touch = None
        self.fractions = [0.0, 0.0, 0.0]
        self.armed = False
        self.active = False
        self.options_pending = False
        self.previous = frozenset()
        self.last_time = None
        self.chord_start = None
        self.chord_fired = False
        self.shortcut_latched = False
        self.nav_direction = None

    def suspend(self):
        """Drop desktop output immediately, retaining only chord tracking."""
        self.sink.release_all()
        self.active = False
        self.armed = False
        self.mouse.clear()
        self.repeats.clear()
        self.touch = None
        self.fractions = [0.0, 0.0, 0.0]
        self.options_pending = False

    def step(self, pad, now, allowed):
        buttons = pad.buttons
        dt = min(0.035, max(0.0, now - self.last_time)) if self.last_time is not None else 0
        self.last_time = now
        chord = {"share", "options"} <= buttons
        if chord:
            self.options_pending = False
            if self.chord_start is None:
                self.chord_start = now
            elif now - self.chord_start >= 0.8 and not self.chord_fired:
                self.chord_fired = True
                self.toggle_mode()
            self.suspend()
            self.previous = buttons
            return
        # Suppress the remaining half of a chord until both buttons are released.
        if self.chord_start is not None:
            if buttons & {"share", "options"}:
                self.previous = buttons
                return
            self.chord_start, self.chord_fired = None, False
            self.previous = buttons
            return
        if not allowed:
            self.suspend()
            self.previous = buttons
            return
        keyboard = self.keyboard_active()
        if keyboard != self.last_keyboard:
            self.suspend()
            self.last_keyboard = keyboard
            self.nav_direction = None
        if not self.active:
            self.active = True
            self.armed = False
        if not self.armed:
            self.armed = pad.neutral(self.settings['deadzone'])
            self.previous = buttons
            self.touch = None
            return

        pressed, released = buttons - self.previous, self.previous - buttons
        # Share is a shortcut layer. Consume its companion buttons until released,
        # even if Share is released first, to avoid a stray click or Backspace.
        if 'share' in buttons:
            if self.mouse:
                self.sink.release_all()
                self.mouse.clear()
            self.shortcut_latched = True
            for name, keys in SHORTCUTS.items():
                if name in pressed:
                    self.sink.hotkey(keys)
            self.options_pending = False
            self.previous = buttons
            return
        if self.shortcut_latched:
            self.shortcut_latched = bool(buttons & (set(SHORTCUTS) | {'options'}))
            self.previous = buttons
            return
        if "options" in pressed:
            self.options_pending = True
        if "share" in buttons:
            self.options_pending = False
        if "options" in released and self.options_pending:
            self.options_pending = False
            self.sink.keyboard()
            self.previous = buttons
            return

        if keyboard:
            direction = next((d for d in ('up', 'down', 'left', 'right') if d in buttons), None)
            if direction is None:
                x, y = pad.lx - 128, pad.ly - 128
                if max(abs(x), abs(y)) > 65:
                    direction = ('right' if x > 0 else 'left') if abs(x) > abs(y) else ('down' if y > 0 else 'up')
            if direction != self.nav_direction:
                self.nav_direction = direction
                self.nav_repeat_at = now + .35
                if direction:
                    self.panel_action(direction)
            elif direction and now >= self.nav_repeat_at:
                self.panel_action(direction)
                self.nav_repeat_at = now + .11
            for button, action in {'cross': 'select', 'circle': 'hide', 'square': 'backspace',
                                   'triangle': 'space', 'l1': 'shift', 'r1': 'enter'}.items():
                if button in pressed:
                    self.panel_action(action)
                    self.repeats[button] = now + .4
                elif button == 'square' and button in buttons and now >= self.repeats.get(button, now + 1):
                    self.panel_action(action)
                    self.repeats[button] = now + .075
        elif 'triangle' in pressed:
            self.sink.keyboard()
            self.previous = buttons
            return

        desired = set()
        if pad.r2 >= 50 or "touch_click" in buttons or ('cross' in buttons and not keyboard):
            desired.add("left")
        if pad.l2 >= 50:
            desired.add("right")
        if "r3" in buttons:
            desired.add("middle")
        for name in self.mouse - desired:
            self.sink.mouse_button(name, False)
        for name in desired - self.mouse:
            self.sink.mouse_button(name, True)
        self.mouse = desired

        for name, keys in ({} if keyboard else KEYS).items():
            if name in pressed:
                self.sink.hotkey(keys)
                self.repeats[name] = now + 0.4
            elif name in buttons and name in REPEAT and now >= self.repeats.get(name, now + 1):
                self.sink.hotkey(keys)
                self.repeats[name] = now + 0.065
            elif name not in buttons:
                self.repeats.pop(name, None)

        slow = 0.25 if "l3" in buttons else 1
        speed, deadzone = self.settings['pointer_speed'], self.settings['deadzone']
        dx = axis(pad.rx, deadzone) * speed * dt * slow
        dy = axis(pad.ry, deadzone) * speed * dt * slow
        if pad.touch and self.touch and pad.touch[0] == self.touch[0]:
            tx, ty = pad.touch[1] - self.touch[1], pad.touch[2] - self.touch[2]
            if abs(tx) < 450 and abs(ty) < 450:
                dx += tx * self.settings['touch_sensitivity'] * slow
                dy += ty * self.settings['touch_sensitivity'] * slow
        self.touch = pad.touch
        self.fractions[0] += dx
        self.fractions[1] += dy
        mx, my = int(self.fractions[0]), int(self.fractions[1])
        self.fractions[0] -= mx
        self.fractions[1] -= my
        if mx or my:
            self.sink.move(mx, my)
        self.fractions[2] += 0 if keyboard else -axis(pad.ly, deadzone) * self.settings['scroll_speed'] * dt
        ticks = int(self.fractions[2])
        if ticks:
            self.fractions[2] -= ticks
            self.sink.scroll(ticks)
        self.previous = buttons
