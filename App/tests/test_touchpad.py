import unittest
from unittest.mock import Mock

from adapter.controller import PadState, parse_report
from adapter.engine import Engine
from adapter.settings import validate
from adapter.touchpad import DoubleTap


class DoubleTapTests(unittest.TestCase):
    def setUp(self):
        self.gesture = DoubleTap()

    def tap(self, start, contact=1, x=500, y=300, duration=.07):
        self.assertFalse(self.gesture.step((contact, x, y), start))
        return self.gesture.step(None, start+duration)

    def test_two_light_taps_produce_one_click_on_second_release(self):
        self.assertFalse(self.tap(.1))
        self.assertTrue(self.tap(.25, contact=2, x=515))
        self.assertFalse(self.gesture.step(None, .4))
        self.assertFalse(self.tap(.5, contact=3))

    def test_single_tap_and_held_finger_never_click(self):
        self.assertFalse(self.tap(.1))
        self.assertFalse(self.gesture.step(None, .7))
        for now in (.8, .9, 1.0, 1.2):
            self.assertFalse(self.gesture.step((2, 500, 300), now))
        self.assertFalse(self.gesture.step(None, 1.3))
        self.assertFalse(self.tap(1.4, contact=3))

    def test_long_touch_rejected_even_without_intermediate_reports(self):
        self.assertFalse(self.tap(.1))
        self.assertFalse(self.tap(.25, contact=2, duration=.4))
        self.assertFalse(self.tap(.75, contact=3))

    def test_slow_distant_and_bouncing_taps_do_not_form_a_pair(self):
        for start, x in ((.7, 500), (.25, 900), (.18, 500)):
            with self.subTest(start=start, x=x):
                self.gesture.reset()
                self.assertFalse(self.tap(.1))
                self.assertFalse(self.tap(start, contact=2, x=x))

    def test_millisecond_contact_glitch_is_not_a_tap(self):
        self.assertFalse(self.tap(.1, duration=.005))
        self.assertFalse(self.tap(.2, contact=2))

    def test_swipe_out_and_back_cannot_become_a_tap(self):
        self.assertFalse(self.tap(.1))
        for touch, now in (((2,500,300),.25), ((2,550,300),.28),
                           ((2,500,300),.31), (None,.34)):
            self.assertFalse(self.gesture.step(touch, now))
        self.assertFalse(self.tap(.45, contact=3))

    def test_contact_handoff_without_release_is_ignored(self):
        self.assertFalse(self.tap(.1))
        self.gesture.step((2,500,300), .25)
        self.gesture.step((3,500,300), .28)
        self.assertFalse(self.gesture.step(None, .32))
        self.assertFalse(self.tap(.4, contact=4))

    def test_button_press_cancels_until_finger_lifts(self):
        self.assertFalse(self.tap(.1))
        self.gesture.step((2,500,300), .25, blocked=True)
        self.gesture.step((2,500,300), .3)
        self.assertFalse(self.gesture.step(None, .35))
        self.assertFalse(self.tap(.45, contact=3))

    def test_missing_touch_samples_cannot_fake_a_finger_lift(self):
        self.assertFalse(self.tap(.1))
        self.gesture.step((2,500,300), .25)
        self.assertFalse(self.gesture.step(None, .3, valid=False))
        self.assertFalse(self.gesture.step((2,500,300), .4))
        self.assertFalse(self.gesture.step(None, .45))
        self.assertFalse(self.tap(.55, contact=3))


class TapMappingTests(unittest.TestCase):
    def setUp(self):
        self.sink = Mock()
        self.cues = []
        self.settings = validate({})
        self.keyboard = False
        self.engine = Engine(self.sink, Mock(), self.settings, lambda: self.keyboard,
                             feedback=self.cues.append)
        self.step(0)
        self.sink.reset_mock()

    def step(self, now, touch=None, allowed=True, **kwargs):
        self.engine.step(PadState(touch=touch, **kwargs), now, allowed)

    def tap(self, now, **kwargs):
        self.step(now, (1,500,300), **kwargs)
        self.step(now+.07, **kwargs)

    def test_click_is_sent_and_released_with_light_feedback(self):
        self.tap(.1)
        self.tap(.25)
        self.assertEqual([call.args for call in self.sink.mouse_button.call_args_list],
                         [('left',True), ('left',False)])
        self.assertEqual(self.cues, ['key'])
        self.sink.move.assert_not_called()

    def test_failed_click_still_releases_without_success_feedback(self):
        self.sink.mouse_button.side_effect = [False, True]
        self.tap(.1)
        self.tap(.25)
        self.sink.mouse_button.assert_called_with('left', False)
        self.assertFalse(self.cues)

    def test_swipes_still_move_pointer_without_clicking(self):
        self.step(.1, (1,500,300))
        self.step(.15, (1,560,330))
        self.step(.2)
        self.tap(.3)
        self.sink.move.assert_called()
        self.sink.mouse_button.assert_not_called()

    def test_physical_press_has_no_extra_tap_click(self):
        self.tap(.1)
        self.step(.25, (2,500,300), buttons=frozenset(['touch_click']))
        self.step(.28, (2,500,300))
        self.step(.32)
        self.tap(.42)
        self.assertEqual([call.args for call in self.sink.mouse_button.call_args_list],
                         [('left',True), ('left',False)])

    def test_pause_focus_reset_and_shortcuts_clear_pending_tap(self):
        for interruption in ('pause', 'focus', 'shortcut'):
            with self.subTest(interruption=interruption):
                self.setUp()
                self.tap(.1)
                if interruption == 'pause':
                    self.step(.2, allowed=False)
                elif interruption == 'focus':
                    self.engine.reset()
                else:
                    self.step(.2, buttons=frozenset(['share']))
                self.step(.21)
                self.tap(.3)
                self.sink.mouse_button.assert_not_called()

    def test_feature_can_be_disabled_and_never_clicks_during_gaming(self):
        for enabled, allowed in ((False, True), (True, False)):
            with self.subTest(enabled=enabled, allowed=allowed):
                self.settings['touch_double_tap'] = enabled
                self.tap(.1, allowed=allowed)
                self.tap(.25, allowed=allowed)
                self.sink.mouse_button.assert_not_called()

    def test_two_finger_touch_and_trigger_hold_cancel_gesture(self):
        for extra in ({'touch_count':2}, {'r2':180}, {'l2':180}):
            with self.subTest(extra=extra):
                self.setUp()
                self.tap(.1)
                self.tap(.25, **extra)
                self.step(.34)
                self.sink.reset_mock()
                self.tap(.42)
                self.sink.mouse_button.assert_not_called()

    def test_tap_click_also_works_with_fast_keyboard_open(self):
        self.keyboard = True
        self.step(.05)
        self.tap(.1)
        self.tap(.25)
        self.assertEqual(self.sink.mouse_button.call_count, 2)

    def test_setting_defaults_on_and_validates_boolean(self):
        self.assertTrue(validate({})['touch_double_tap'])
        self.assertFalse(validate({'touch_double_tap':False})['touch_double_tap'])
        self.assertTrue(validate({'touch_double_tap':'false'})['touch_double_tap'])

    def test_parser_counts_both_contacts_for_usb_and_bluetooth(self):
        for bluetooth in (False, True):
            data = bytearray(78 if bluetooth else 64)
            data[0] = 0x11 if bluetooth else 1
            base = 3 if bluetooth else 1
            data[base+32] = 1
            data[base+34:base+42] = bytes([1, 0xf4, 0xc1, 0x12, 2, 0xf4, 0xc1, 0x12])
            pad = parse_report(data, bluetooth)
            self.assertEqual(pad.touch_count, 2)
            self.assertTrue(pad.touch_valid)
            self.assertEqual(pad.touch, (1,500,300))
            data[base+34] |= 128
            pad = parse_report(data, bluetooth)
            self.assertEqual(pad.touch_count, 1)
            self.assertEqual(pad.touch, (2,500,300))
            data[base+32] = 0
            self.assertFalse(parse_report(data, bluetooth).touch_valid)
        self.assertFalse(parse_report(bytes([1,128,128,128,128,8,0,0,0,0]), True).touch_valid)


if __name__ == '__main__':
    unittest.main()
