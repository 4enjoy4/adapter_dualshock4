import ctypes as C
from ctypes import wintypes as W
import logging
import queue
import threading
import time
from dataclasses import dataclass

from .controller import Controller
from .engine import Engine
from .feedback import Feedback
from . import settings as config
from .windows import GameGuard, InputSink, RegisterHotKey, UnregisterHotKey, PeekMessageW, steam_game_roots, GetForegroundWindow


@dataclass(frozen=True)
class Request:
    kind: str
    action: object
    epoch: int
    hwnd: int
    created: float


class Service(threading.Thread):
    def __init__(self, settings):
        super().__init__(name='DS4 input', daemon=True)
        self.settings = settings.copy()
        self.mode = settings['mode']
        self.commands = queue.Queue()
        self.ui_requests = queue.Queue()
        self.keyboard_visible = threading.Event()
        self.desktop_allowed = threading.Event()
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.status = {'connected': False, 'reason': 'Looking for your DualShock 4…',
                       'mode': self.mode, 'active': False, 'armed': False, 'reports': 0}
        self.report_count = 0
        self.input_epoch = 0
        self._last_hwnd = 0

    def snapshot(self):
        with self.lock:
            return self.status.copy()

    def command(self, name, value=None):
        self.commands.put((name, value))

    def request(self, kind, action=None):
        return Request(kind, action, self.input_epoch, self._last_hwnd, time.monotonic())

    def request_valid(self, request, hwnd):
        return (self.mode == 'auto' and self.desktop_allowed.is_set()
                and request.epoch == self.input_epoch and request.hwnd == hwnd
                and 0 <= time.monotonic() - request.created <= .35)

    def post_ui(self, kind, action=None):
        self.ui_requests.put(self.request(kind, action))

    def feedback(self, cue):
        self.command('feedback', self.request('feedback', cue))

    def toggle(self):
        self.mode = 'auto' if self.mode == 'gaming' else 'gaming'
        self.settings['mode'] = self.mode
        config.save(self.settings)
        logging.info('Mode changed to %s', self.mode)

    def run(self):
        controller, sink, guard = Controller(), InputSink(), GameGuard()
        feedback = Feedback(controller.set_rumble)
        sink.keyboard_callback = lambda: self.post_ui('keyboard')
        sink.hide_keyboard_callback = lambda: self.post_ui('hide_keyboard')
        engine = Engine(sink, self.toggle, self.settings, self.keyboard_visible.is_set,
                        lambda action: self.post_ui('panel', action), self.feedback)
        hotkey = bool(RegisterHotKey(None, 1, 0x4000 | 0x0001 | 0x0002, 0x7B))
        retry_at = 0
        pad = None
        last_status = 0
        last_reason = None
        error = ''
        try:
            while not self.stopping.is_set():
                try:
                    keyboard_requested = False
                    feedback_requested = False
                    while True:
                        try:
                            name, value = self.commands.get_nowait()
                        except queue.Empty:
                            break
                        if name == 'mode':
                            self.mode = value
                            self.settings['mode'] = value
                            config.save(self.settings)
                        elif name == 'toggle':
                            self.toggle()
                        elif name == 'settings':
                            if value.get('keyboard_mode') != self.settings['keyboard_mode']:
                                engine.reset()
                                self.input_epoch += 1
                            self.settings = config.validate({**value, 'mode': self.mode})
                            engine.settings = self.settings
                            config.save(self.settings)
                        elif name == 'keyboard':
                            keyboard_requested = True
                        elif name == 'test_feedback':
                            feedback_requested = True
                        elif name == 'feedback':
                            if (controller.device and self.settings['feedback_enabled']
                                    and self.request_valid(value, GetForegroundWindow())
                                    and time.monotonic() - controller.last_report < .35):
                                feedback.pulse(value.action, time.monotonic(), self.settings['feedback_strength'])
                        elif name == 'rescan':
                            self.input_epoch += 1
                            guard.roots = steam_game_roots()
                            engine.reset()
                            feedback.stop()
                            controller.close()
                            pad = None
                            retry_at = 0
                    msg = W.MSG()
                    while PeekMessageW(C.byref(msg), None, 0x0312, 0x0312, 1):
                        if msg.wParam == 1:
                            self.toggle()
                    now = time.monotonic()
                    foreground = guard.foreground()
                    reason = guard.reason(foreground, self.settings, self.mode)
                    if reason:
                        self.desktop_allowed.clear()
                        self.keyboard_visible.clear()
                    else:
                        self.desktop_allowed.set()
                    if reason:
                        engine.suspend()
                        if reason != last_reason:
                            self.input_epoch += 1
                            sink.hide_keyboard()
                    if foreground.hwnd != self._last_hwnd:
                        # A click or held key must never cross a focus transition.
                        engine.reset()
                        self.input_epoch += 1
                        feedback.stop()
                    self._last_hwnd = foreground.hwnd
                    last_reason = reason
                    if keyboard_requested and not reason:
                        sink.keyboard()
                    if controller.device is None and now >= retry_at:
                        if controller.connect():
                            error = ''
                            engine.reset()
                            feedback.reconnect()
                            logging.info('Connected to DualShock 4 PID %04x', controller.product)
                        retry_at = now + 1.5
                    if controller.device:
                        for _ in range(64):
                            sample, had_data = controller.read()
                            if not had_data:
                                break
                            if sample:
                                pad = sample
                                self.report_count += 1
                                # Chord callbacks can change mode in the middle of a batch.
                                allowed = not reason and self.mode == 'auto'
                                engine.step(pad, time.monotonic(), allowed)
                        age = time.monotonic() - controller.last_report
                        if age > 0.35:
                            if engine.active:
                                self.input_epoch += 1
                            engine.suspend()
                        if age > 2.0:
                            feedback.stop()
                            controller.close()
                            engine.reset()
                            pad = None
                            error = 'Controller stopped sending input. Reconnecting…'
                    feedback_allowed = (not reason and self.mode == 'auto'
                                        and bool(controller.device) and time.monotonic()-controller.last_report < .35
                                        and self.settings['feedback_enabled'] and self.settings['feedback_strength'] > 0)
                    # Apply settings and game detection before a user-requested test.
                    if feedback_requested and feedback_allowed:
                        feedback.pulse('enter', time.monotonic(), self.settings['feedback_strength'])
                    feedback.tick(time.monotonic(), allowed=feedback_allowed)
                    if now - last_status >= .2:
                        connected = bool(controller.device and pad and now - controller.last_report < .35)
                        text = reason or ('Desktop controls active' if engine.armed else 'Release sticks and buttons to enable desktop controls')
                        if not connected:
                            text = error or 'Waiting for controller — press PS to reconnect'
                        with self.lock:
                            self.status = {
                                'connected': connected, 'reason': text, 'mode': self.mode,
                                'active': connected and engine.active and not reason,
                                'armed': engine.armed, 'reports': self.report_count,
                                'battery': pad.battery if pad else None,
                                'charging': pad.charging if pad else False,
                                'transport': pad.transport if pad else '',
                                'buttons': sorted(pad.buttons) if pad else [],
                                'foreground': foreground.exe, 'fullscreen': foreground.full,
                                'steam_roots': len(guard.roots), 'hotkey': hotkey,
                                'error': sink.error or error or feedback.error,
                            }
                        last_status = now
                    self.stopping.wait(.008 if controller.device else .15)
                except Exception as exc:
                    logging.exception('Input service recovered from an error')
                    engine.reset()
                    self.input_epoch += 1
                    feedback.stop()
                    controller.close()
                    pad = None
                    error = str(exc)
                    with self.lock:
                        self.status.update(connected=False, active=False, armed=False,
                                           reason=error, error=error)
                    retry_at = time.monotonic() + 2
                    self.stopping.wait(.25)
        finally:
            engine.reset()
            feedback.stop()
            controller.close()
            if hotkey:
                UnregisterHotKey(None, 1)

    def stop(self):
        self.stopping.set()
        self.join(timeout=3)
