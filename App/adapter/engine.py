"""Pure input translation. No Windows calls: pause and release behavior is testable."""
import math
from .navigation import Navigation
from .touchpad import DoubleTap

KEYS = {
    "circle": (0x1B,), "square": (0x08,),
    "up": (0x26,), "down": (0x28,), "left": (0x25,), "right": (0x27,),
    "l1": (0x11, 0x10, 0x09), "r1": (0x11, 0x09),
}
PANEL_BUTTONS = {'cross': 'select', 'circle': 'hide', 'square': 'backspace',
                 'triangle': 'space', 'l1': 'shift', 'r1': 'enter'}
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
    def __init__(self, sink, toggle_mode, settings, keyboard_active=lambda: False, panel_action=lambda action: None, feedback=lambda cue: None):
        self.sink, self.toggle_mode, self.settings = sink, toggle_mode, settings
        self.feedback = feedback
        self.previous = frozenset()
        self.active = False
        self.armed = False
        self.last_time = None
        self.mouse = set()
        self.repeats = {}
        self.touch = None
        self.double_tap = DoubleTap()
        self.fractions = [0.0, 0.0, 0.0]
        self.chord_start = None
        self.chord_fired = False
        self.options_pending = False
        self.keyboard_active = keyboard_active
        self.panel_action = panel_action
        self.last_keyboard = False
        self.shortcut_latched = False
        self.navigation = {side: Navigation() for side in ('left', 'right', 'dpad')}
        self.triggers = set()
        self.last_layout = self.settings.get('keyboard_mode', 'dual')

    def reset(self):
        self.suspend()
        self.previous = frozenset()
        self.last_time = None
        self.chord_start = None
        self.chord_fired = False

    def suspend(self):
        """Release desktop input and require neutral, retaining chord tracking."""
        self.sink.release_all()
        self.active = self.armed = False
        self.mouse.clear()
        self.repeats.clear()
        self.touch = None
        self.double_tap.reset()
        self.fractions = [0.0, 0.0, 0.0]
        self.options_pending = False
        self.shortcut_latched = False
        self.triggers.clear()
        for navigation in self.navigation.values():
            navigation.reset()

    def keyboard_step(self, pad, pressed, now):
        speed = self.settings.get('keyboard_speed', 1.25)
        dual = self.settings.get('keyboard_mode', 'dual') == 'dual'
        # D-pad can cross the whole keyboard; each stick stays on its own half.
        direction = self.navigation['dpad'].step(128, 128, now, speed, pad.buttons)
        if direction:
            self.panel_action(direction)
        for side, x, y in [('left', pad.lx, pad.ly), ('right', pad.rx, pad.ry)]:
            if side == 'right' and not dual:
                continue
            direction = self.navigation[side].step(x, y, now, speed)
            if direction:
                self.panel_action(('move', side, direction) if dual else direction)
        if dual:
            for side, value in [('left', pad.l2), ('right', pad.r2)]:
                if value >= 110 and side not in self.triggers:
                    self.triggers.add(side)
                    self.panel_action(('select', side))
                elif value <= 55:
                    self.triggers.discard(side)
        for button, action in PANEL_BUTTONS.items():
            if button in pressed:
                self.panel_action(action)
                self.repeats[button] = now + .32
            elif button == 'square' and button in pad.buttons and now >= self.repeats.get(button, now + 1):
                self.panel_action(action)
                self.repeats[button] = now + .06

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
        layout = self.settings.get('keyboard_mode', 'dual')
        if keyboard != self.last_keyboard or layout != self.last_layout:
            self.suspend()
            self.last_keyboard = keyboard
            self.last_layout = layout
        if not self.active:
            self.active = True
            self.armed = False
        if not self.armed:
            self.armed = pad.neutral(self.settings['deadzone'])
            self.previous = buttons
            self.touch = None
            return

        pressed, released = buttons - self.previous, self.previous - buttons
        tap_blocked = (not self.settings.get('touch_double_tap', True) or bool(buttons)
                       or pad.l2 >= 40 or pad.r2 >= 40 or pad.touch_count > 1)
        tap_clicked = self.double_tap.step(pad.touch, now, blocked=tap_blocked, valid=pad.touch_valid)
        # Share is a shortcut layer. Consume its companion buttons until released,
        # even if Share is released first, to avoid a stray click or Backspace.
        if 'share' in buttons:
            if self.mouse:
                self.sink.release_all()
                self.mouse.clear()
            self.shortcut_latched = True
            for name, keys in SHORTCUTS.items():
                if name in pressed:
                    if self.sink.hotkey(keys) is not False:
                        self.feedback('shortcut')
            self.options_pending = False
            self.touch = None
            self.fractions = [0.0, 0.0, 0.0]
            for navigation in self.navigation.values():
                navigation.reset()
            self.previous = buttons
            return
        if self.shortcut_latched:
            self.shortcut_latched = bool(buttons or pad.l2 > 55 or pad.r2 > 55)
            self.previous = buttons
            return
        if "options" in pressed:
            self.options_pending = True
        if "options" in released and self.options_pending:
            self.options_pending = False
            self.sink.keyboard()
            self.previous = buttons
            return

        if keyboard:
            self.keyboard_step(pad, pressed, now)
        elif 'triangle' in pressed:
            self.sink.keyboard()
            self.previous = buttons
            return

        dual = keyboard and layout == 'dual'
        desired = set()
        if (pad.r2 >= 50 and not dual) or "touch_click" in buttons or ('cross' in buttons and not keyboard):
            desired.add("left")
        if pad.l2 >= 50 and not dual:
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
        dx = 0 if dual else axis(pad.rx, deadzone) * speed * dt * slow
        dy = 0 if dual else axis(pad.ry, deadzone) * speed * dt * slow
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
        if tap_clicked:
            down = self.sink.mouse_button('left', True)
            up = self.sink.mouse_button('left', False)
            if down is not False and up is not False:
                self.feedback('key')
        self.previous = buttons
