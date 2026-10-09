import unittest
from dataclasses import replace
from unittest.mock import patch

from adapter.controller import PadState, parse_report
from adapter.engine import Engine, axis
from adapter.settings import validate
from adapter.windows import Foreground, GameGuard
from adapter.keyboard_model import KeyboardModel, panel_geometry


class Recorder:
    def __init__(self):
        self.events = []
    def release_all(self): self.events.append(('release',))
    def mouse_button(self, *args): self.events.append(('button', *args))
    def move(self, *args): self.events.append(('move', *args))
    def scroll(self, *args): self.events.append(('scroll', *args))
    def hotkey(self, keys): self.events.append(('key', tuple(keys)))
    def keyboard(self): self.events.append(('keyboard',))


def report(bluetooth=False):
    data = bytearray(78 if bluetooth else 64)
    data[0] = 0x11 if bluetooth else 1
    base = 3 if bluetooth else 1
    data[base:base + 4] = bytes([128, 127, 190, 45])
    data[base + 4] = 8
    data[base + 29] = 5
    data[base + 32] = 1
    data[base + 34] = 0x80
    data[base + 38] = 0x80
    return data, base


class ReportTests(unittest.TestCase):
    def test_usb_and_bluetooth_same_controls(self):
        for bluetooth in (False, True):
            data, base = report(bluetooth)
            data[base + 4] = 0x20 | 1  # Cross + diagonal up/right
            data[base + 5] = 0x20 | 0x10  # Options + Share
            data[base + 8] = 200
            state = parse_report(data)
            self.assertEqual(state.buttons, {'cross', 'up', 'right', 'options', 'share'})
            self.assertEqual(state.r2, 200)
            self.assertEqual(state.battery, 60)
            self.assertEqual(state.transport, 'Bluetooth' if bluetooth else 'USB')

    def test_touch_coordinates_and_inactive(self):
        for bluetooth in (False, True):
            data, base = report(bluetooth)
            data[base + 34:base + 38] = bytes([7, 0xDC, 0xC5, 0x21])  # x=1500,y=540
            self.assertEqual(parse_report(data).touch, (7, 1500, 540))
            data[base + 34] |= 128
            self.assertIsNone(parse_report(data).touch)

    def test_minimal_bluetooth_has_no_fake_touch_or_battery(self):
        data = bytearray([1, 128, 128, 128, 128, 8, 0, 0, 0, 0])
        for sample in (data, data + bytes(68)):
            state = parse_report(sample, bluetooth=True)
            self.assertIsNone(state.battery)
            self.assertIsNone(state.touch)
            self.assertTrue(state.neutral())

    def test_malformed_reports_ignored(self):
        for data in ([], [1], [17] * 12, [99] * 78):
            self.assertIsNone(parse_report(data))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.sink = Recorder()
        self.toggles = []
        self.engine = Engine(self.sink, lambda: self.toggles.append(True), validate({}))
        self.engine.step(PadState(), 0, True)

    def step(self, time, buttons=(), allowed=True, **kw):
        self.engine.step(PadState(buttons=frozenset(buttons), **kw), time, allowed)

    def test_options_on_release_opens_keyboard_once(self):
        self.step(.1, ['options'])
        self.step(.2, ['options'])
        self.assertNotIn(('keyboard',), self.sink.events)
        self.step(.3)
        self.step(.4)
        self.assertEqual(self.sink.events.count(('keyboard',)), 1)

    def test_pause_chord_never_opens_keyboard(self):
        self.step(.1, ['options'])
        self.step(.2, ['options', 'share'])
        self.step(1.1, ['options', 'share'])
        self.step(2, ['options', 'share'])
        self.step(2.1, ['options'])
        self.step(2.2)
        self.assertEqual(len(self.toggles), 1)
        self.assertNotIn(('keyboard',), self.sink.events)

    def test_short_chord_cancels_keyboard(self):
        self.step(.1, ['options', 'share'])
        self.step(.2, ['options'])
        self.step(.3)
        self.assertFalse(self.toggles)
        self.assertNotIn(('keyboard',), self.sink.events)

    def test_game_mode_blocks_all_desktop_outputs_but_allows_resume(self):
        self.step(.1, ['cross', 'square', 'options'], allowed=False, rx=255, r2=255)
        self.step(.2, allowed=False)
        self.assertTrue(all(e[0] == 'release' for e in self.sink.events))
        self.step(.3, ['share', 'options'], allowed=False)
        self.step(1.2, ['share', 'options'], allowed=False)
        self.assertEqual(len(self.toggles), 1)

    def test_held_click_released_on_pause(self):
        self.step(.1, r2=255)
        self.assertIn(('button', 'left', True), self.sink.events)
        self.step(.2, r2=255, allowed=False)
        self.assertEqual(self.sink.events[-1], ('release',))
        self.assertFalse(self.engine.mouse)

    def test_resume_requires_neutral_before_click(self):
        self.step(.1, allowed=False)
        self.sink.events.clear()
        self.step(.2, r2=255)
        self.step(.3, r2=255)
        self.assertEqual(self.sink.events, [])
        self.step(.4)
        self.step(.5, r2=255)
        self.assertEqual(self.sink.events, [('button', 'left', True)])

    def test_reset_releases_click_and_rearms_safely(self):
        self.step(.1, r2=255)
        self.engine.reset()
        self.assertEqual(self.sink.events[-1], ('release',))
        self.assertFalse(self.engine.armed)
        self.step(.2, ['cross'])
        self.assertFalse(any(e[0] == 'key' for e in self.sink.events))

    def test_mouse_drag_and_shared_touch_click(self):
        self.step(.1, ['touch_click'], r2=255)
        self.step(.2, r2=255)
        self.step(.3)
        self.assertEqual(self.sink.events, [('button', 'left', True), ('button', 'left', False)])

    def test_backspace_repeats_while_cross_holds_one_click(self):
        self.step(.1, ['square', 'cross'])
        self.step(.6, ['square', 'cross'])
        self.assertEqual(self.sink.events.count(('key', (0x08,))), 2)
        self.assertEqual(self.sink.events.count(('button', 'left', True)), 1)
        self.assertNotIn(('key', (0x0D,)), self.sink.events)
        self.step(.7)
        self.assertEqual(self.sink.events[-1], ('button','left',False))

    def test_shortcuts_consume_normal_action_even_when_share_released_first(self):
        for button, code in [('square',67),('triangle',86),('cross',65),('circle',88),('l1',90),('r1',89)]:
            self.engine.reset()
            self.step(0)
            self.sink.events.clear()
            self.step(.1, ['share',button])
            self.step(.2, [button])
            self.step(.8, [button])
            self.step(.9)
            self.assertEqual(self.sink.events, [('key',(17,code))])

    def test_keyboard_navigation_consumes_desktop_keys_clicks_and_scroll(self):
        actions = []
        self.engine.keyboard_active = lambda: True
        self.engine.panel_action = actions.append
        self.step(.05)
        self.sink.events.clear()
        self.step(.1, ['right'])
        self.step(.3, ['right'])
        self.step(.5, ['right'])
        self.step(.6)
        self.step(.7, ['cross'])
        self.step(.8)
        self.step(.9, ['l1'])
        self.step(1)
        self.step(1.1, ly=255)
        self.assertEqual(actions, ['right','right','select','shift','down'])
        self.assertEqual(self.sink.events, [])

    def test_closing_keyboard_does_not_leak_held_cross_click(self):
        visible = [True]
        self.engine.keyboard_active = lambda: visible[0]
        self.step(.1)
        self.step(.2,['cross'])
        visible[0] = False
        self.sink.events.clear()
        self.step(.3,['cross'])
        self.step(.4,['cross'])
        self.assertNotIn(('button','left',True),self.sink.events)
        self.step(.5)
        self.step(.6,['cross'])
        self.assertEqual(self.sink.events[-1],('button','left',True))

    def test_gaming_blocks_shortcuts_and_keyboard_selection(self):
        actions = []
        self.engine.keyboard_active = lambda: True
        self.engine.panel_action = actions.append
        self.step(.1)
        self.sink.events.clear()
        self.step(.2,['share','triangle'],allowed=False)
        self.step(.3,['right','cross'],allowed=False)
        self.assertFalse(actions)
        self.assertTrue(all(e == ('release',) for e in self.sink.events))

    def test_centered_stick_does_not_drift(self):
        for i in range(1, 40):
            self.step(i / 100, rx=135, ry=118, ly=130)
        self.assertFalse(self.sink.events)

    def test_pointer_movement_and_precision(self):
        self.step(.02, rx=255)
        normal = self.sink.events[-1][1]
        self.step(.04, ['l3'], rx=255)
        slow = self.sink.events[-1][1]
        self.assertGreater(normal, slow * 3)

    def test_touch_recontact_does_not_jump(self):
        self.step(.1, touch=(1, 200, 200))
        self.step(.2, touch=(1, 210, 200))
        self.assertTrue(any(e[0] == 'move' for e in self.sink.events))
        self.sink.events.clear()
        self.step(.3, touch=(2, 1100, 700))
        self.assertFalse(self.sink.events)


class GuardTests(unittest.TestCase):
    def setUp(self):
        with patch('adapter.windows.steam_game_roots', return_value=('d:\\steam\\steamapps\\common\\',)):
            self.guard = GameGuard()
        self.settings = validate({})

    def test_fullscreen_game_is_paused(self):
        self.assertTrue(self.guard.reason(Foreground(1, 'game.exe', full=True), self.settings, 'auto'))

    def test_windowed_steam_game_is_paused(self):
        fg = Foreground(1, 'game.exe', 'd:\\steam\\steamapps\\common\\game\\bin\\game.exe')
        self.assertTrue(self.guard.reason(fg, self.settings, 'auto'))

    def test_windowed_saved_game_is_paused(self):
        self.settings['game_apps'] = ['game.exe']
        self.assertTrue(self.guard.reason(Foreground(1, 'game.exe'), self.settings, 'auto'))

    def test_desktop_and_keyboard_are_exempt(self):
        self.assertFalse(self.guard.reason(Foreground(1, 'explorer.exe', full=True, shell=True), self.settings, 'auto'))
        self.assertFalse(self.guard.reason(Foreground(1, 'osk.exe', full=True), self.settings, 'auto'))

    def test_manual_gaming_always_pauses(self):
        self.assertTrue(self.guard.reason(Foreground(1, 'explorer.exe', shell=True), self.settings, 'gaming'))

    def test_game_folder_boundary(self):
        fg = Foreground(1, 'app.exe', 'd:\\steam\\steamapps\\common-malicious\\app.exe')
        self.assertFalse(self.guard.reason(fg, self.settings, 'auto'))


class SettingsTests(unittest.TestCase):
    def test_bad_settings_cannot_remove_deadzone_or_overflow_speed(self):
        settings = validate({'deadzone': 1, 'pointer_speed': 'fast', 'game_apps': None, 'mode': 'desktop'})
        self.assertEqual(settings['deadzone'], .18)
        self.assertEqual(settings['pointer_speed'], 1100)
        self.assertEqual(settings['game_apps'], [])
        self.assertEqual(settings['mode'], 'auto')


class KeyboardTests(unittest.TestCase):
    def test_directional_selection_and_row_alignment(self):
        model = KeyboardModel()
        self.assertEqual(model.selected(),('text','q'))
        model.move('right')
        self.assertEqual(model.selected(),('text','w'))
        model.move('down')
        self.assertEqual(model.selected(),('text','s'))
        model.move('up')
        self.assertEqual(model.selected(),('text','w'))
        for _ in range(30): model.move('down')
        self.assertEqual(model.row,4)

    def test_language_and_shift_change_selected_character(self):
        model = KeyboardModel()
        model.shift = True
        self.assertEqual(model.selected(),('text','Q'))
        model.language = 'RU'
        self.assertEqual(model.selected(),('text','Й'))

    def test_keyboard_fits_work_area_with_taskbar_at_any_edge(self):
        for work in [(0,0,2880,1704),(-1920,0,0,1040),(80,40,1366,768)]:
            for size in ('small','compact','large'):
                for dock in ('top','bottom'):
                    x,y,w,h = panel_geometry(work,2,size,dock)
                    self.assertGreaterEqual(x,work[0])
                    self.assertGreaterEqual(y,work[1])
                    self.assertLessEqual(x+w,work[2])
                    self.assertLessEqual(y+h,work[3])


if __name__ == '__main__':
    unittest.main()
