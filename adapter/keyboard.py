"""Compact, non-activating keyboard with controller selection and pointer support."""
import ctypes as C
from ctypes import wintypes as W
import tkinter as tk
from .windows import bind, user32, InputSink, GetForegroundWindow, monitor_work_area
from .keyboard_model import KeyboardModel, panel_geometry

LRESULT = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
SetWindowLongPtrW = bind(user32, 'SetWindowLongPtrW', [W.HWND, C.c_int, C.c_ssize_t], C.c_ssize_t)
GetWindowLongPtrW = bind(user32, 'GetWindowLongPtrW', [W.HWND, C.c_int], C.c_ssize_t)
CallWindowProcW = bind(user32, 'CallWindowProcW', [C.c_void_p, W.HWND, W.UINT, W.WPARAM, W.LPARAM], LRESULT)
GetAncestor = bind(user32, 'GetAncestor', [W.HWND, W.UINT], W.HWND)
SetWindowPos = bind(user32, 'SetWindowPos', [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT], W.BOOL)


class KeyboardPanel:
    def __init__(self, root, settings=None, on_visibility=lambda shown: None, on_settings=lambda: None,
                 feedback=lambda cue: None):
        self.root, self.settings, self.on_visibility = root, settings if settings is not None else {}, on_visibility
        self.on_settings = on_settings
        self.feedback = feedback
        self.window = self.canvas = None
        self.shown = False
        self.model = KeyboardModel(self.settings.get('keyboard_mode', 'dual') == 'dual')
        self.sink = InputSink()
        self.old_proc = self.proc = self.hwnd = None
        self.target = None
        self.keys, self.key_indices = [], []
        self.drag_origin = None
        self.moved = False
        self.draw_job = None
        self.scale = float(root.tk.call('tk', 'scaling')) / (96 / 72)

    def toggle(self):
        if self.shown:
            self.hide()
            self.feedback('close')
            return
        self.target = GetForegroundWindow()
        self.work = monitor_work_area(self.target)
        if self.window is None:
            self.create()
        self.model.shift = False
        self.place()
        self.draw()
        self.window.deiconify()
        self.window.update_idletasks()
        SetWindowPos(self.hwnd, W.HWND(-1), 0, 0, 0, 0, 0x0010 | 0x0001 | 0x0002)
        self.shown = True
        self.on_visibility(True)
        self.feedback('open')

    def place(self):
        self.x, self.y, self.width, self.height = panel_geometry(self.work, self.scale,
            self.settings.get('keyboard_size', 'compact'), self.settings.get('keyboard_dock', 'bottom'))
        self.window.geometry(f'{self.width}x{self.height}{self.x:+d}{self.y:+d}')
        SetWindowPos(self.hwnd, W.HWND(-1), self.x, self.y, self.width, self.height, 0x0010)

    def create(self):
        window = self.window = tk.Toplevel(self.root)
        window.withdraw()
        window.title('DS4 Keyboard')
        window.overrideredirect(True)
        self.canvas = tk.Canvas(window, bg='#0d1729', highlightthickness=1, highlightbackground='#3c567b', takefocus=False)
        self.canvas.pack(fill='both', expand=True)
        window.update_idletasks()
        self.hwnd = GetAncestor(window.winfo_id(), 2)
        SetWindowLongPtrW(self.hwnd, -20, GetWindowLongPtrW(self.hwnd, -20) | 0x08000000 | 0x80)
        @WNDPROC
        def procedure(hwnd, msg, wp, lp):
            if msg == 0x0021:
                return 3
            return CallWindowProcW(self.old_proc, hwnd, msg, wp, lp)
        self.proc = procedure
        self.old_proc = SetWindowLongPtrW(self.hwnd, -4, C.cast(self.proc, C.c_void_p).value)
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.click)

    def rows(self):
        return self.model.rows()

    def draw(self):
        c = self.canvas
        c.delete('all')
        self.keys, self.key_indices = [], []
        w, h = self.width, self.height
        title, footer = h * .14, h * .11
        fs = max(13, round(w / 63))
        small = max(12, round(fs * .76))
        gap = max(4, round(w / 230))
        c.create_text(14, title/2, text=f'KEYBOARD  {self.model.language}   /   DRAG TO MOVE', anchor='w', fill='#93accd', font=('Segoe UI Semibold', -small))
        mode_label = 'Fast' if self.model.dual else 'Classic'
        for offset, label, action, size in ((315, mode_label, 'mode',78), (230, 'Size', 'size',65), (152, 'Top / bottom', 'dock',87), (58, 'Close', 'hide',48)):
            unit = w / 760
            x1, x2 = w-offset*unit, w-(offset-size)*unit
            c.create_rectangle(x1, 6, x2, title-5, fill='#22334c', outline='')
            c.create_text((x1+x2)/2, title/2, text=label, fill='#d9e7fb', font=('Segoe UI', -small))
            self.keys.append((x1, 6, x2, title-5, (action, None)))
            self.key_indices.append(None)
        area = h-title-footer
        positions = self.model.positions()
        colors = {'left': '#80c7ff', 'right': '#7de3b4'}
        for ri, row in enumerate(self.rows()):
            y1 = title + ri*area/5
            y2 = y1 + area/5 - gap
            unit, x = (w-20) / sum(k[2] for k in row), 10
            for ci, (label, action, weight) in enumerate(row):
                x2 = x + unit*weight-gap
                selected = next((side for side, pos in positions.items() if pos == (ri,ci)), None)
                toggled = action[0] == 'shift' and self.model.shift or action[0] == 'caps' and self.model.caps
                fill = colors[selected] if selected else '#25594f' if toggled else '#1d2a40'
                active = selected == self.model.active
                c.create_rectangle(x,y1,x2,y2,fill=fill,outline='#ffffff' if active else '#30435f',width=3 if active else 1)
                if self.model.dual:
                    side = 'left' if ci in self.model.columns(ri, 'left') else 'right'
                    c.create_line(x,y2,x2,y2,fill=colors[side],width=2)
                c.create_text((x+x2)/2,(y1+y2)/2,text=label,fill='#08111f' if selected else '#f0f5ff',font=('Segoe UI Semibold',-fs))
                self.keys.append((x,y1,x2,y2,action))
                self.key_indices.append((ri,ci))
                x += unit*weight
        hint = (f'LS + L2  Blue     RS + R2  Green     X  {self.model.active.title()} key     △  Space     □  Delete     R1  Enter'
                if self.model.dual else 'D-pad / LS  Move     X  Select     ○  Close     □  Delete     △  Space     L1  Shift     R1  Enter')
        c.create_text(w/2,h-footer/2,text=hint,fill='#a9bfdd',font=('Segoe UI',-small))

    def redraw(self):
        if self.draw_job is None:
            self.draw_job = self.root.after_idle(self.flush_draw)

    def flush_draw(self):
        self.draw_job = None
        if self.shown:
            self.draw()

    def sync_layout(self):
        self.model.dual = self.settings.get('keyboard_mode', 'dual') == 'dual'
        active = self.model.active
        for side in self.model.positions():
            self.model.selected(side)
        self.model.active = active
        self.redraw()

    def handle(self, action):
        if not self.shown:
            return
        if isinstance(action, tuple):
            if action[0] == 'move':
                self.model.move(action[2], action[1])
            elif action[0] == 'select':
                self.activate(self.model.selected(action[1]))
        elif action in ('up','down','left','right'):
            self.model.move(action)
        elif action == 'select':
            self.activate(self.model.selected())
        elif action in ('hide','shift'):
            self.activate((action,None))
        elif action == 'space':
            self.activate(('text',' '))
        elif action in ('backspace','enter'):
            self.activate(('key',(8 if action == 'backspace' else 13,)))
        if self.shown:
            self.redraw()

    def activate(self, action):
        kind, value = action
        if kind == 'hide':
            self.hide()
            self.feedback('close')
        elif kind in ('shift','caps'):
            setattr(self.model, kind, not getattr(self.model,kind))
            self.feedback('edit')
        elif kind == 'language':
            self.model.language = 'RU' if self.model.language == 'EN' else 'EN'
            self.sync_layout()
        elif kind == 'mode':
            self.settings['keyboard_mode'] = 'single' if self.model.dual else 'dual'
            self.sync_layout()
            self.on_settings()
        elif kind == 'size':
            choices = ['small','compact','large']
            self.settings['keyboard_size'] = choices[(choices.index(self.settings.get('keyboard_size','compact'))+1)%3]
            self.place()
            self.on_settings()
        elif kind == 'dock':
            self.settings['keyboard_dock'] = 'top' if self.settings.get('keyboard_dock','bottom') == 'bottom' else 'bottom'
            self.place()
            self.on_settings()
        elif kind == 'text':
            if self.sink.text(value) is not False:
                self.model.shift = False
                self.feedback('key')
            else:
                self.feedback('error')
        elif kind == 'key':
            cue = 'enter' if value == (13,) else 'shortcut' if 17 in value else 'edit'
            self.feedback(cue if self.sink.hotkey(value) is not False else 'error')

    def press(self, event):
        self.moved = False
        if event.y < self.height*.14 and event.x < self.width*(1-315/760):
            self.drag_origin = (event.x_root,event.y_root,self.window.winfo_x(),self.window.winfo_y())

    def drag(self, event):
        if self.drag_origin:
            ox,oy,wx,wy = self.drag_origin
            left,top,right,bottom = self.work
            x = max(left,min(right-self.width,wx+event.x_root-ox))
            y = max(top,min(bottom-self.height,wy+event.y_root-oy))
            SetWindowPos(self.hwnd,None,x,y,0,0,0x0010|0x0001|0x0004)
            self.moved = True

    def click(self, event):
        self.drag_origin = None
        if self.moved:
            return
        for i,(x1,y1,x2,y2,action) in enumerate(self.keys):
            if x1<=event.x<=x2 and y1<=event.y<=y2:
                if self.key_indices[i] is not None:
                    self.model.select_at(*self.key_indices[i])
                self.activate(action)
                if self.shown:
                    self.redraw()
                break

    def hide(self):
        if self.window:
            self.window.withdraw()
        self.shown = False
        self.on_visibility(False)
        self.sink.release_all()

    def close(self):
        self.hide()
        if self.draw_job is not None:
            self.root.after_cancel(self.draw_job)
            self.draw_job = None
        if self.hwnd and self.old_proc:
            SetWindowLongPtrW(self.hwnd,-4,self.old_proc)
        if self.window:
            self.window.destroy()
        self.window = None
