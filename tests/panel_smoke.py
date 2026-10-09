"""Real SendInput -> adapter keyboard -> text field test in a disposable owned UI."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapter.keyboard import KeyboardPanel, GetAncestor
from adapter.controller import PadState
from adapter.engine import Engine
from adapter.settings import validate
from adapter.windows import (InputSink, GetForegroundWindow, GetWindowThreadProcessId,
                             GetCursorPos, bind, user32, dpi_aware)

dpi_aware()
root = tk.Tk()
root.title('DS4 Keyboard Verification')
root.geometry('900x330+160+120')
tk.Label(root, text='Temporary adapter test — no input is sent to other applications.', font=('Segoe UI', 12)).pack(pady=18)
entry = tk.Entry(root, font=('Segoe UI', 18))
entry.pack(fill='x', padx=20, pady=20)
entry.focus_set()
panel = KeyboardPanel(root)
sink = InputSink()
results = {}
cursor = W.POINT()
GetCursorPos(C.byref(cursor))
set_cursor = bind(user32, 'SetCursorPos', [C.c_int, C.c_int], W.BOOL)
from_point = bind(user32, 'WindowFromPoint', [W.POINT], W.HWND)

def wait(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(.01)

def pad_press(buttons=(), **kwargs):
    if not owns_focus():
        raise RuntimeError('Test target lost focus; stopping input')
    engine.step(PadState(buttons=frozenset(buttons), **kwargs), time.monotonic(), True)
    wait(.06)
    engine.step(PadState(), time.monotonic(), True)
    wait(.06)

def owns_focus():
    pid = W.DWORD()
    GetWindowThreadProcessId(GetForegroundWindow(), C.byref(pid))
    return pid.value == os.getpid()

try:
    root.update()
    for i in range(300):
        if owns_focus(): break
        wait(.1)
    if not owns_focus(): raise RuntimeError('Activate the temporary test window to continue.')
    entry.focus_set()
    before = GetForegroundWindow()
    panel.toggle()
    wait(.4)
    results['opening_keeps_text_field_focus'] = GetForegroundWindow() == before and root.focus_get() == entry
    if not results['opening_keeps_text_field_focus']: raise RuntimeError('Keyboard stole focus')
    # Exercise the same mouse sink used by the R2 mapping against our own panel.
    x1,y1,x2,y2,action = next(k for k in panel.keys if k[4] == ('text','q'))
    x = panel.canvas.winfo_rootx() + int((x1+x2)/2)
    y = panel.canvas.winfo_rooty() + int((y1+y2)/2)
    hit = from_point(W.POINT(x,y))
    if GetAncestor(hit,2) != panel.hwnd: raise RuntimeError('Another window covers the test key')
    set_cursor(x,y)
    wait(.1)
    emitted = []
    original_text = panel.sink.text
    def record_text(value):
        emitted.append(value)
        original_text(value)
    panel.sink.text = record_text
    sink.mouse_button('left',True); wait(.05)
    sink.mouse_button('left',False); wait(.25)
    results['controller_click_types_character'] = entry.get() == 'q'
    results['typed_text'] = entry.get()
    results['emitted_text'] = emitted
    results['sink_error'] = panel.sink.error or sink.error
    results['click_keeps_target_focus'] = GetForegroundWindow() == before
    engine = Engine(sink, lambda: None, validate({}), lambda: panel.shown, panel.handle)
    engine.step(PadState(),time.monotonic(),True)
    pad_press(['right'])
    pad_press(['cross'])
    results['dpad_and_cross_type_selected_key'] = entry.get() == 'qw'
    pad_press(lx=255)
    pad_press(['cross'])
    results['left_stick_navigates_without_moving_text_caret'] = entry.get() == 'qwe'
    pad_press(['l1'])
    pad_press(['cross'])
    pad_press(['triangle'])
    results['shift_and_space_shortcuts'] = entry.get() == 'qweE '
    pad_press(['square'])
    results['square_backspace'] = entry.get() == 'qweE'
    pad_press(['share','cross'])
    pad_press(['share','square'])
    pad_press(['share','triangle'])
    results['copy_paste_without_stray_delete'] = entry.get() == 'qweE'
    pad_press(['share','triangle'])
    results['paste_inserts_clipboard_text'] = entry.get() == 'qweEqweE'
    left,top,right,bottom = panel.work
    results['keyboard_excludes_taskbar'] = panel.y+panel.height < bottom
    panel.activate(('size',None)); panel.draw(); wait(.05)
    results['resized_keyboard_excludes_taskbar'] = panel.y+panel.height < bottom
    panel.activate(('dock',None)); panel.draw(); wait(.05)
    results['top_dock_inside_work_area'] = panel.y >= top and panel.y+panel.height < bottom
    pad_press(['circle'])
    results['circle_hides_keyboard'] = not panel.shown
    results['keyboard_navigation_keeps_target_focus'] = GetForegroundWindow() == before
    panel.toggle(); wait(.05)
    panel.toggle(); wait(.1)
    results['panel_hides'] = not panel.shown
    panel.toggle(); wait(.2)
    results['panel_reopens_without_focus_loss'] = panel.shown and GetForegroundWindow() == before
    results['success'] = all(value for value in results.values() if isinstance(value,bool)) and not results['sink_error']
except Exception as exc:
    results.update(success=False,error=str(exc))
finally:
    sink.release_all()
    panel.close()
    root.destroy()
    set_cursor(cursor.x,cursor.y)
    Path('panel-smoke.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
raise SystemExit(0 if results.get('success') else 1)
