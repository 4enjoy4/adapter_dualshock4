import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from adapter.controller import Controller, PadState
from adapter.engine import Engine
from adapter.feedback import Feedback, rumble_report
from adapter.keyboard_model import KeyboardModel
from adapter.navigation import Navigation
from adapter.service import Service
from adapter.settings import validate
from adapter.windows import Foreground, GameGuard


class FeedbackTests(unittest.TestCase):
    def test_usb_motor_order_and_unrelated_features_untouched(self):
        report = rumble_report(False, 100, 150)
        self.assertEqual(len(report), 32)
        self.assertEqual(report[:6], bytes([5, 1, 0, 0, 150, 100]))
        self.assertEqual(report[6:], bytes(26))

    def test_bluetooth_report_and_crc_vector(self):
        report = rumble_report(True, 100, 150)
        self.assertEqual(len(report), 78)
        self.assertEqual(report[:8], bytes([17, 196, 0, 1, 0, 0, 150, 100]))
        # Reflected CRC-32, HID output prefix 0xA2, little-endian trailer.
        self.assertEqual(report[-4:], bytes.fromhex('7c5573d7'))
        self.assertEqual(report[8:-4], bytes(66))

    def test_pulse_expires_and_idle_does_not_keep_overwriting_game_rumble(self):
        writes = []
        feedback = Feedback(lambda l,r: writes.append((l,r)))
        feedback.pulse('enter', 1, 1)
        feedback.tick(1.05)
        self.assertEqual(len(writes), 1)
        feedback.tick(1.11)
        for _ in range(20): feedback.tick(2, allowed=False)
        self.assertEqual(writes, [(180,110),(0,0)])

    def test_pause_stops_immediately_and_drops_small_overlap(self):
        writes = []
        feedback = Feedback(lambda l,r: writes.append((l,r)))
        feedback.pulse('enter',1)
        feedback.pulse('key',1.02)
        feedback.tick(1.03,allowed=False)
        self.assertEqual(len(writes),2)
        self.assertEqual(writes[-1],(0,0))

    def test_failed_haptics_stop_and_disable_until_reconnect(self):
        writer = Mock(side_effect=OSError('write failed'))
        feedback = Feedback(writer)
        feedback.pulse('key',1)
        feedback.pulse('enter',2)
        self.assertEqual(writer.call_count,2)  # Start and best-effort stop only.
        self.assertTrue(feedback.error)
        feedback.reconnect()
        writer.side_effect = None
        feedback.pulse('enter',3)
        self.assertTrue(feedback.active)

    def test_close_stops_owned_motors_before_closing_handle(self):
        controller = Controller()
        controller.device = Mock()
        device = controller.device
        device.write.side_effect = lambda data: len(data)
        controller.set_rumble(80, 90)
        controller.close()
        self.assertEqual(device.write.call_args.args[0],rumble_report(False))
        device.close.assert_called_once()

    def test_successful_cleanup_keeps_failed_start_warning(self):
        writer = Mock(side_effect=[OSError('write failed'), None])
        feedback = Feedback(writer)
        feedback.pulse('key', 1)
        self.assertFalse(feedback.active)
        self.assertTrue(feedback.failed)
        self.assertTrue(feedback.error)
        feedback.reconnect()
        self.assertFalse(feedback.error)

    def test_windows_padded_hid_write_is_successful(self):
        controller = Controller()
        controller.bluetooth = True
        controller.device = Mock()
        controller.device.write.return_value = 547
        controller.set_rumble(80,90)
        self.assertTrue(controller.rumble_active)
        controller.device.write.return_value = 10
        with self.assertRaises(OSError):
            controller.set_rumble(0,0)


class FastTypingTests(unittest.TestCase):
    def setUp(self):
        self.model = KeyboardModel(dual=True)
        self.sink = Mock()
        self.settings = validate({})
        self.actions = []
        self.engine = Engine(self.sink, Mock(), self.settings, lambda: True, self.actions.append)
        self.engine.step(PadState(), 0, True)

    def test_independent_cursors_and_dpad_crossing_split(self):
        self.model.move('right','left')
        self.model.move('right','right')
        self.assertEqual(self.model.selected('left'),('text','w'))
        self.assertEqual(self.model.selected('right'),('text','u'))
        self.model.select_at(1,5)
        self.model.move('right')
        self.assertEqual(self.model.selected(),('text','y'))
        self.assertEqual(self.model.active,'right')
        self.assertEqual(self.model.selected('left'),('text','t'))

    def test_every_key_reachable_in_both_languages(self):
        for language in ('EN','RU'):
            self.model.language = language
            for row, keys in enumerate(self.model.rows()):
                columns = self.model.columns(row,'left') + self.model.columns(row,'right')
                self.assertEqual(columns,list(range(len(keys))))
                for col in columns:
                    self.model.select_at(row,col)
                    self.assertEqual(self.model.selected(),keys[col][1])

    def test_both_sticks_and_triggers_type_without_mouse_output(self):
        pad = PadState(lx=255,rx=255,l2=180,r2=180)
        self.sink.reset_mock()
        self.engine.step(pad,.1,True)
        self.assertEqual(self.actions,[('move','left','right'),('move','right','right'),
                                       ('select','left'),('select','right')])
        self.sink.move.assert_not_called()
        self.sink.mouse_button.assert_not_called()
        self.sink.scroll.assert_not_called()

    def test_trigger_hysteresis_avoids_repeat_or_bounce(self):
        for i,value in enumerate([120,100,130,80,120,50,120],1):
            self.engine.step(PadState(l2=value),i*.01,True)
        self.assertEqual(self.actions,[('select','left'),('select','left')])

    def test_layout_switch_requires_neutral_before_mouse_click(self):
        self.engine.step(PadState(r2=180),.1,True)
        self.settings['keyboard_mode'] = 'single'
        self.engine.step(PadState(r2=180),.2,True)
        self.sink.mouse_button.assert_not_called()
        self.engine.step(PadState(),.3,True)
        self.engine.step(PadState(r2=180),.4,True)
        self.sink.mouse_button.assert_called_once_with('left',True)

    def test_shortcut_release_does_not_type_a_held_trigger(self):
        self.engine.step(PadState(buttons=frozenset(['share','square']),r2=180),.1,True)
        self.engine.step(PadState(r2=180),.2,True)
        self.engine.step(PadState(r2=180),.3,True)
        self.assertFalse(self.actions)
        self.engine.step(PadState(),.4,True)
        self.engine.step(PadState(r2=180),.5,True)
        self.assertEqual(self.actions,[('select','right')])

    def test_stick_diagonal_jitter_does_not_alternate_axes(self):
        nav = Navigation()
        self.assertEqual(nav.step(218,210,0),'right')
        self.assertIsNone(nav.step(210,218,.01))
        self.assertIsNone(nav.step(218,210,.02))
        self.assertEqual(nav.step(128,255,.03),'down')

    def test_held_navigation_is_faster_than_old_repeat(self):
        nav = Navigation()
        count = sum(nav.step(255,128,i/100) is not None for i in range(100))
        self.assertGreaterEqual(count,13)  # Previous 350/110 ms repeat: 7 in one second.


class RoutingTests(unittest.TestCase):
    def test_old_foreground_expired_and_paused_requests_are_dropped(self):
        service = Service(validate({}))
        service.desktop_allowed.set()
        service._last_hwnd = 123
        request = service.request('panel','select')
        self.assertTrue(service.request_valid(request,123))
        self.assertFalse(service.request_valid(request,456))
        self.assertFalse(service.request_valid(replace(request,created=request.created-1),123))
        service.input_epoch += 1
        self.assertFalse(service.request_valid(request,123))
        request = service.request('panel','select')
        service.mode = 'gaming'
        self.assertFalse(service.request_valid(request,123))

    def test_video_remains_controllable_even_with_fullscreen_opt_in(self):
        with patch('adapter.windows.steam_game_roots',return_value=()):
            guard = GameGuard()
        settings = validate({'version':2,'auto_fullscreen':True})
        for exe in ('chrome.exe','msedge.exe','firefox.exe','vlc.exe','mpv.exe'):
            self.assertFalse(guard.reason(Foreground(1,exe,full=True),settings,'auto'))
        self.assertTrue(guard.reason(Foreground(1,'game.exe',full=True),settings,'auto'))
        settings['game_apps'] = ['chrome.exe']
        self.assertTrue(guard.reason(Foreground(1,'chrome.exe',full=True),settings,'auto'))

    def test_old_fullscreen_setting_migrates_without_losing_games(self):
        old = validate({'auto_fullscreen':True,'game_apps':['game.exe']})
        self.assertFalse(old['auto_fullscreen'])
        self.assertEqual(old['game_apps'],['game.exe'])
        self.assertTrue(validate({'version':2,'auto_fullscreen':True})['auto_fullscreen'])

    def test_fullscreen_desktop_circle_still_sends_escape(self):
        with patch('adapter.windows.steam_game_roots',return_value=()):
            guard = GameGuard()
        settings = validate({})
        allowed = not guard.reason(Foreground(1,'video-app.exe',full=True),settings,'auto')
        sink = Mock()
        engine = Engine(sink,Mock(),settings)
        engine.step(PadState(),0,allowed)
        engine.step(PadState(buttons=frozenset(['circle'])),.1,allowed)
        sink.hotkey.assert_called_once_with((27,))


if __name__ == '__main__':
    unittest.main()
