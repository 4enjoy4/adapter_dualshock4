"""Explicit integration check. Sends input only to its own temporary test window."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapter.windows import (InputSink, GameGuard, GetForegroundWindow, GetCursorPos,
                             FindWindowW, IsWindowVisible, SetForegroundWindow,
                             GetWindowThreadProcessId, ShowWindow, user32, bind, dpi_aware)
from adapter.settings import validate


def main():
    dpi_aware()
    result = {}
    previous = GetForegroundWindow()
    cursor = W.POINT()
    GetCursorPos(C.byref(cursor))
    set_cursor = bind(user32, 'SetCursorPos', [C.c_int, C.c_int], W.BOOL)
    sink = InputSink()
    root = tk.Tk()
    root.title('DS4 Adapter — temporary input verification')
    root.geometry('620x260+180+140')
    tk.Label(root, text='Testing controller adapter input. This window closes automatically.', font=('Segoe UI', 12)).pack(pady=24)
    entry = tk.Entry(root, font=('Segoe UI', 16))
    entry.pack(fill='x', padx=30)
    clicks = []
    target = tk.Label(root, text='Mouse click test area', bg='#c0eadc', height=3)
    target.pack(fill='x', padx=30, pady=20)
    target.bind('<ButtonPress-1>', lambda e: clicks.append('down'))
    target.bind('<ButtonRelease-1>', lambda e: clicks.append('up'))
    def wait(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            time.sleep(.01)
    opened_keyboard = False
    try:
        root.update()
        ancestor = bind(user32, 'GetAncestor', [W.HWND, W.UINT], W.HWND)
        hwnd = ancestor(root.winfo_id(), 2)
        ShowWindow(hwnd, 5)
        root.attributes('-topmost', True)
        root.lift()
        SetForegroundWindow(hwnd)
        root.focus_force()
        entry.focus_force()
        wait(.3)
        guard = GameGuard()
        foreground_pid = W.DWORD()
        GetWindowThreadProcessId(GetForegroundWindow(), C.byref(foreground_pid))
        result['owned_window_has_focus'] = foreground_pid.value == os.getpid()
        if not result['owned_window_has_focus']:
            result['foreground_exe'] = guard.foreground().exe
            raise RuntimeError('Test window did not receive focus; input test skipped.')
        sink.hotkey((0x41,))
        wait(.15)
        result['keyboard_input'] = entry.get().lower() == 'a'
        set_cursor(target.winfo_rootx() + 50, target.winfo_rooty() + 25)
        start = W.POINT()
        GetCursorPos(C.byref(start))
        sink.move(12, 0)
        wait(.1)
        moved = W.POINT()
        GetCursorPos(C.byref(moved))
        result['mouse_movement'] = moved.x > start.x
        sink.mouse_button('left', True)
        wait(.05)
        sink.mouse_button('left', False)
        wait(.1)
        result['mouse_click'] = clicks == ['down', 'up']
        root.attributes('-fullscreen', True)
        wait(.25)
        fg = guard.foreground()
        result['real_fullscreen_detection'] = fg.full and bool(guard.reason(fg, validate({}), 'auto'))
        root.attributes('-fullscreen', False)
        wait(.25)
        result['desktop_resumes'] = not guard.reason(guard.foreground(), validate({}), 'auto')
        osk = FindWindowW('OSKMainClass', None)
        already_open = bool(osk and IsWindowVisible(osk))
        if already_open:
            result['windows_keyboard_open'] = True
            result['windows_keyboard_close'] = 'skipped: already open before test'
        else:
            sink.keyboard()
            for _ in range(50):
                wait(.1)
                osk = FindWindowW('OSKMainClass', None)
                if osk and IsWindowVisible(osk):
                    opened_keyboard = True
                    break
            result['windows_keyboard_open'] = opened_keyboard
            if opened_keyboard:
                sink.hide_keyboard()
                wait(.5)
                osk = FindWindowW('OSKMainClass', None)
                result['windows_keyboard_close'] = not (osk and IsWindowVisible(osk))
                if result['windows_keyboard_close']:
                    opened_keyboard = False
        result['sendinput_error'] = sink.error
        result['success'] = all(value is True or isinstance(value, str) for value in result.values()) and not sink.error
    except Exception as exc:
        result.update(success=False, error=str(exc))
    finally:
        sink.release_all()
        if opened_keyboard:
            sink.keyboard()
            wait(.3)
        root.destroy()
        set_cursor(cursor.x, cursor.y)
        if previous:
            SetForegroundWindow(previous)
    output = Path(__file__).resolve().parents[1] / 'windows-smoke.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())
