import ctypes as C
from ctypes import wintypes as W
import logging
import queue
import threading
import time

from .controller import Controller
from .engine import Engine
from . import settings as config
from .windows import GameGuard, InputSink, RegisterHotKey, UnregisterHotKey, PeekMessageW, steam_game_roots


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

    def snapshot(self):
        with self.lock:
            return self.status.copy()

    def command(self, name, value=None):
        self.commands.put((name, value))

    def toggle(self):
        self.mode = 'auto' if self.mode == 'gaming' else 'gaming'
        self.settings['mode'] = self.mode
        config.save(self.settings)
        logging.info('Mode changed to %s', self.mode)

    def run(self):
        controller, sink, guard = Controller(), InputSink(), GameGuard()
        sink.keyboard_callback = lambda: self.ui_requests.put('keyboard')
        sink.hide_keyboard_callback = lambda: self.ui_requests.put('hide_keyboard')
        engine = Engine(sink, self.toggle, self.settings, self.keyboard_visible.is_set,
                        lambda action: self.ui_requests.put(('panel', action, self.input_epoch)))
        hotkey = bool(RegisterHotKey(None, 1, 0x4000 | 0x0001 | 0x0002, 0x7B))
        retry_at = 0
        pad = None
        last_status = 0
        last_reason = None
        error = ''
        try:
            while not self.stopping.is_set():
                try:
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
                            self.settings = config.validate({**value, 'mode': self.mode})
                            engine.settings = self.settings
                            config.save(self.settings)
                        elif name == 'keyboard':
                            if self.mode == 'auto':
                                sink.keyboard()
                        elif name == 'rescan':
                            self.input_epoch += 1
                            guard.roots = steam_game_roots()
                            engine.reset()
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
                    if foreground.hwnd != getattr(self, '_last_hwnd', foreground.hwnd):
                        # A click or held key must never cross a focus transition.
                        engine.reset()
                        self.input_epoch += 1
                    self._last_hwnd = foreground.hwnd
                    last_reason = reason
                    if controller.device is None and now >= retry_at:
                        if controller.connect():
                            error = ''
                            engine.reset()
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
                            controller.close()
                            engine.reset()
                            pad = None
                            error = 'Controller stopped sending input. Reconnecting…'
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
                                'error': sink.error or error,
                            }
                        last_status = now
                    self.stopping.wait(.008 if controller.device else .15)
                except Exception as exc:
                    logging.exception('Input service recovered from an error')
                    engine.reset()
                    self.input_epoch += 1
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
            controller.close()
            if hotkey:
                UnregisterHotKey(None, 1)

    def stop(self):
        self.stopping.set()
        self.join(timeout=3)
