import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from PIL import Image, ImageDraw

from . import settings as config
from .windows import visible_apps, startup_enabled, set_startup, InputSink
from .keyboard import KeyboardPanel
from .controller_view import ControllerView
from .windows import monitor_work_area, GetForegroundWindow

TITLE = 'DS4 Desktop Adapter'


def icon_image():
    im = Image.new('RGBA', (64, 64), '#101b2e')
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((8, 18, 56, 49), radius=12, fill='#65e0be')
    draw.rectangle((17, 26, 21, 40), fill='#101b2e')
    draw.rectangle((12, 31, 26, 35), fill='#101b2e')
    draw.ellipse((40, 26, 46, 32), fill='#101b2e')
    draw.ellipse((46, 34, 52, 40), fill='#101b2e')
    return im


class App:
    def __init__(self, service, settings, minimized=False):
        self.service, self.settings = service, settings
        self.root = tk.Tk()
        self.root.title(TITLE)
        # Tk fonts scale with Windows DPI, but geometry/padding are pixel values.
        # Give scaled text enough space on high-DPI laptop displays.
        scale = float(self.root.tk.call('tk', 'scaling')) / (96 / 72)
        self.scale = scale
        left, top, right, bottom = monitor_work_area()
        width = min(round(1080 * scale), right-left-60)
        height = min(round(790 * scale), bottom-top-70)
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(width, round(940 * scale)), min(height, round(700 * scale)))
        self.root.configure(bg='#0b1423')
        self.ui_events = queue.Queue()
        self.tray = None
        self.tray_ready = False
        self.last_mode = None
        self.closing = False
        self.keyboard = KeyboardPanel(self.root, self.settings, self.keyboard_visibility,
                                      self.save_panel_settings, self.service.feedback)
        self.last_status_at = 0
        self.native_input = InputSink()
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#0b1423', foreground='#edf4ff')
        style.configure('TFrame', background='#0b1423')
        style.configure('TNotebook', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(18, 9), background='#142238')
        style.map('TNotebook.Tab', background=[('selected', '#264565')], foreground=[('selected', '#ffffff')])
        style.configure('TEntry', fieldbackground='#142238', foreground='#edf4ff', insertcolor='#edf4ff')
        style.configure('TScale', troughcolor='#263952')
        style.configure('TButton', background='#1d334e', bordercolor='#304761')
        style.map('TButton', background=[('active','#294d70'), ('disabled','#142238')], foreground=[('disabled','#718198')])
        style.map('TCheckbutton', background=[('active','#0b1423')])
        style.configure('TButton', padding=(12, 7))
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 22))
        style.configure('Sub.TLabel', foreground='#99aecb')
        style.configure('Status.TLabel', font=('Segoe UI Semibold', 13))
        style.configure('Card.TFrame', background='#142238')
        style.configure('Card.TLabel', background='#142238')
        style.configure('CardTitle.TLabel', background='#142238', font=('Segoe UI Semibold', 12))
        style.configure('TCheckbutton', padding=(0, 6))
        body = ttk.Frame(self.root, padding=round(20*scale))
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Take control.', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='DUALSHOCK 4  /  WINDOWS ADAPTER', style='Sub.TLabel').pack(anchor='w', pady=(4, 18))
        self.status = tk.StringVar(value='Connecting to your controller…')
        self.details = tk.StringVar(value='Bluetooth and USB supported')
        self.status_label = ttk.Label(body, textvariable=self.status, style='Status.TLabel', wraplength=width-64)
        self.status_label.pack(anchor='w')
        ttk.Label(body, textvariable=self.details, style='Sub.TLabel').pack(anchor='w', pady=(4, 14))

        bar = ttk.Frame(body)
        bar.pack(fill='x', pady=(0, 16))
        self.auto_button = ttk.Button(bar, text='Automatic desktop / game', command=lambda: self.service.command('mode', 'auto'))
        self.auto_button.pack(side='left', padx=(0, 8))
        self.game_button = ttk.Button(bar, text='Pause for gaming', command=lambda: self.service.command('mode', 'gaming'))
        self.game_button.pack(side='left')
        self.keyboard_button = ttk.Button(bar, text='Open keyboard', command=lambda: self.service.command('keyboard'))
        self.keyboard_button.pack(side='right')

        tabs = ttk.Notebook(body)
        tabs.pack(fill='both', expand=True)
        controls, typing, games, preferences = (ttk.Frame(tabs, padding=16) for _ in range(4))
        tabs.add(controls, text='Controls')
        tabs.add(typing, text='Typing & vibration')
        tabs.add(games, text='Games')
        tabs.add(preferences, text='Settings')
        self.build_controls(controls)
        self.build_games(games)
        self.build_settings(preferences)
        self.build_typing(typing)

        self.warning = tk.StringVar()
        ttk.Label(body, textvariable=self.warning, foreground='#f2bf76', wraplength=width-64).pack(anchor='w', pady=(12, 6))
        footer = ttk.Frame(body)
        footer.pack(fill='x', pady=(4, 0))
        ttk.Label(footer, text='Share + Options (hold) or Ctrl + Alt + F12: pause / resume', style='Sub.TLabel').pack(side='left')
        ttk.Button(footer, text='Quit', command=self.quit).pack(side='right')
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        self.root.bind('<Control-q>', lambda e: self.quit())
        self.start_tray()
        if minimized:
            self.root.after(1000, self.hide)
        self.root.after(100, self.refresh)

    def build_controls(self, parent):
        guide_bar = ttk.Frame(parent)
        guide_bar.pack(fill='x', pady=(0, 12))
        for mode in ('Desktop', 'Keyboard', 'Shortcuts'):
            ttk.Button(guide_bar, text=mode, command=lambda value=mode: self.controller_view.update_state(mode=value)).pack(side='left', padx=(0,8))
        ttk.Label(guide_bar, text='Control guides. Shortcuts always work in desktop mode.', style='Sub.TLabel').pack(side='right')
        self.controller_view = ControllerView(parent, self.scale)
        self.controller_view.pack(fill='both', expand=True)
        ttk.Label(parent, text='TRY IT  ·  Options opens the keyboard. Fast: LS + L2 / RS + R2. D-pad + X also works.', style='Sub.TLabel').pack(anchor='w', pady=(12,5))
        self.test_entry = ttk.Entry(parent)
        self.test_entry.pack(fill='x', ipady=4)

    def keyboard_visibility(self, shown):
        if shown:
            self.service.keyboard_visible.set()
            self.controller_view.update_state(mode='Keyboard')
        else:
            self.service.keyboard_visible.clear()
            if hasattr(self, 'controller_view') and self.controller_view.mode == 'Keyboard':
                self.controller_view.update_state(mode='Desktop')

    def save_panel_settings(self):
        if hasattr(self, 'fast_typing'):
            self.fast_typing.set(self.settings['keyboard_mode'] == 'dual')
        self.service.command('settings', self.settings.copy())

    def build_typing(self, parent):
        ttk.Label(parent, text='Keep both thumbs on the sticks.', style='Status.TLabel').pack(anchor='w', pady=(0,8))
        ttk.Label(parent, text='Fast typing gives each hand its own selection.\nBlue: left stick + L2. Green: right stick + R2.\nX types the key with a white outline. D-pad can cross the whole keyboard.\nTriangle: Space. Square: Backspace. L1: Shift. R1: Enter.', style='Sub.TLabel').pack(anchor='w')
        self.fast_typing = tk.BooleanVar(value=self.settings['keyboard_mode'] == 'dual')
        ttk.Checkbutton(parent, text='Fast typing with both sticks and triggers', variable=self.fast_typing).pack(anchor='w', pady=(12,0))
        ttk.Label(parent, text='Classic typing keeps the right stick and triggers as mouse controls.\nYou can also switch using Fast / Classic in the keyboard header.', style='Sub.TLabel').pack(anchor='w', pady=(0,12))
        for key, label, low, high in [('keyboard_speed','Navigation speed',.7,2), ('feedback_strength','Vibration strength',0,1)]:
            ttk.Label(parent, text=label).pack(anchor='w')
            self.variables[key] = tk.DoubleVar(value=self.settings[key])
            ttk.Scale(parent, from_=low, to=high, variable=self.variables[key]).pack(fill='x', pady=(4,12))
        self.variables['feedback_enabled'] = tk.BooleanVar(value=self.settings['feedback_enabled'])
        ttk.Checkbutton(parent, text='Vibration feedback', variable=self.variables['feedback_enabled']).pack(anchor='w')
        ttk.Label(parent, text='Light taps for typing, a stronger pulse for Enter, and confirmation for shortcuts.\nVibration stops when desktop controls pause.', style='Sub.TLabel').pack(anchor='w', pady=(0,12))
        ttk.Button(parent, text='Save typing settings', command=self.apply_settings).pack(side='left')
        ttk.Button(parent, text='Test vibration', command=self.test_feedback).pack(side='left', padx=10)

    def test_feedback(self):
        self.save_preferences()
        self.service.command('test_feedback')

    def build_games(self, parent):
        ttk.Label(parent, text='Desktop input pauses while these apps have focus.', font=('Segoe UI Semibold', 11)).pack(anchor='w')
        ttk.Label(parent, text='Steam games pause desktop controls automatically. Add other games below.\nFullscreen video keeps working: Circle sends Escape to leave fullscreen.', style='Sub.TLabel').pack(anchor='w', pady=(6, 10))
        self.games_list = tk.Listbox(parent, height=6, font=('Segoe UI', 10), bg='#142238', fg='#edf4ff', selectbackground='#315b85', borderwidth=0, highlightthickness=1, highlightbackground='#304761')
        self.games_list.pack(fill='x')
        self.update_games_list()
        actions = ttk.Frame(parent)
        actions.pack(fill='x', pady=8)
        ttk.Button(actions, text='Add running game', command=self.choose_running).pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Choose game .exe', command=self.choose_exe).pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Remove', command=self.remove_game).pack(side='left')
        ttk.Label(parent, text='For any game: hold Share + Options for 0.8 seconds to pause.\nRepeat after playing to return to automatic mode.\n\nIf Steam also moves the mouse, turn off its desktop layout under\nSteam > Settings > Controller. Keep game layouts enabled.', style='Sub.TLabel').pack(anchor='w', pady=(10, 0))

    def build_settings(self, parent):
        self.variables = {}
        for row, (key, title, low, high) in enumerate((
            ('pointer_speed', 'Pointer speed', 150, 3000),
            ('touch_sensitivity', 'Touchpad sensitivity', .2, 4),
            ('scroll_speed', 'Scroll speed', 1, 25),
            ('deadzone', 'Stick deadzone', .08, .4),
        )):
            variable = tk.DoubleVar(value=self.settings[key])
            self.variables[key] = variable
            ttk.Label(parent, text=title).grid(row=row, column=0, sticky='w', pady=8)
            ttk.Scale(parent, from_=low, to=high, variable=variable).grid(row=row, column=1, sticky='ew', padx=14)
        parent.columnconfigure(1, weight=1)
        for row, (key, title) in enumerate((
            ('auto_fullscreen', 'Also pause in unknown fullscreen apps (optional)'),
            ('auto_steam_games', 'Detect games in Steam libraries'),
        ), 4):
            variable = tk.BooleanVar(value=self.settings[key])
            self.variables[key] = variable
            ttk.Checkbutton(parent, text=title, variable=variable).grid(row=row, column=0, columnspan=2, sticky='w')
        self.native_keyboard = tk.BooleanVar(value=self.settings['keyboard_type'] == 'windows')
        ttk.Checkbutton(parent, text='Use Windows keyboard (pointer only; no D-pad selection)', variable=self.native_keyboard).grid(row=6, column=0, columnspan=2, sticky='w')
        self.startup = tk.BooleanVar(value=startup_enabled())
        ttk.Checkbutton(parent, text='Start in tray when I sign in to Windows', variable=self.startup).grid(row=7, column=0, columnspan=2, sticky='w')
        ttk.Button(parent, text='Apply settings', command=self.apply_settings).grid(row=8, column=0, sticky='w', pady=(12, 8))
        ttk.Button(parent, text='Reconnect controller', command=lambda: self.service.command('rescan')).grid(row=8, column=1, sticky='e')
        ttk.Label(parent, text='Normal user permissions. Administrator prompts and the sign-in screen\nmay need your laptop keyboard or touchpad.', style='Sub.TLabel').grid(row=9, column=0, columnspan=2, sticky='w', pady=8)

    def update_games_list(self):
        self.games_list.delete(0, 'end')
        for name in self.settings['game_apps']:
            self.games_list.insert('end', name)

    def add_game(self, exe):
        self.settings['game_apps'] = sorted(set(self.settings['game_apps']) | {exe.lower()})
        self.service.command('settings', self.settings.copy())
        self.update_games_list()

    def choose_running(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('Choose a running game')
        dialog.geometry('610x340')
        dialog.transient(self.root)
        apps = visible_apps()
        selection = tk.Listbox(dialog, font=('Segoe UI', 10))
        selection.pack(fill='both', expand=True, padx=16, pady=16)
        for exe, title in apps:
            selection.insert('end', f'{exe}  —  {title}')
        def add():
            if selection.curselection():
                self.add_game(apps[selection.curselection()[0]][0])
                dialog.destroy()
        ttk.Button(dialog, text='Pause desktop input for this app', command=add).pack(pady=(0, 16))

    def choose_exe(self):
        path = filedialog.askopenfilename(parent=self.root, title='Choose game executable', filetypes=[('Windows applications', '*.exe')])
        if path:
            self.add_game(Path(path).name)

    def remove_game(self):
        indices = self.games_list.curselection()
        if indices:
            name = self.games_list.get(indices[0])
            self.settings['game_apps'].remove(name)
            self.service.command('settings', self.settings.copy())
            self.update_games_list()

    def apply_settings(self):
        try:
            set_startup(self.startup.get())
            self.save_preferences()
            messagebox.showinfo(TITLE, 'Settings saved.', parent=self.root)
        except OSError as exc:
            messagebox.showerror(TITLE, str(exc), parent=self.root)

    def save_preferences(self):
        self.settings.update({key: var.get() for key, var in self.variables.items()})
        keyboard_type = 'windows' if self.native_keyboard.get() else 'adapter'
        if keyboard_type != self.settings['keyboard_type']:
            self.keyboard.hide()
            self.native_input.hide_keyboard()
        self.settings['keyboard_type'] = keyboard_type
        self.settings['keyboard_mode'] = 'dual' if self.fast_typing.get() else 'single'
        self.keyboard.sync_layout()
        self.service.command('settings', self.settings.copy())

    def start_tray(self):
        try:
            import pystray
            def put(name):
                return lambda *args: self.ui_events.put(name)
            self.tray = pystray.Icon('DS4DesktopAdapter', icon_image(), TITLE, menu=pystray.Menu(
                pystray.MenuItem('Open adapter', put('show'), default=True),
                pystray.MenuItem('Pause / resume desktop controls', put('toggle')),
                pystray.MenuItem('Quit', put('quit')),
            ))
            def setup(icon):
                icon.visible = True
                self.tray_ready = True
            threading.Thread(target=lambda: self.tray.run(setup=setup), daemon=True, name='Tray').start()
        except Exception:
            logging.exception('Tray unavailable')

    def refresh(self):
        if self.closing:
            return
        while not self.service.ui_requests.empty():
            action = self.service.ui_requests.get_nowait()
            if action.kind == 'hide_keyboard':
                self.keyboard.hide()
                self.native_input.hide_keyboard()
            elif not self.service.request_valid(action, GetForegroundWindow()):
                continue
            elif action.kind == 'panel' and self.service.keyboard_visible.is_set():
                self.keyboard.handle(action.action)
            elif action.kind == 'keyboard':
                if self.settings['keyboard_type'] == 'windows':
                    self.native_input.keyboard()
                else:
                    self.keyboard.toggle()
        while not self.ui_events.empty():
            event = self.ui_events.get_nowait()
            if event == 'quit':
                self.quit()
                return
            if event == 'show':
                self.root.deiconify()
                self.root.lift()
            elif event == 'toggle':
                self.service.command('toggle')
        if time.monotonic() - self.last_status_at < .2:
            self.root.after(16, self.refresh)
            return
        self.last_status_at = time.monotonic()
        state = self.service.snapshot()
        self.controller_view.update_state(buttons=state.get('buttons', []))
        self.status.set(state['reason'])
        self.status_label.configure(foreground='#76dfb9' if state['active'] and state['armed'] else '#f2bf76')
        if state['connected']:
            battery = f"  ·  Battery {state['battery']}%" if state.get('battery') is not None else ''
            self.details.set(f"Connected over {state.get('transport', '')}{battery}")
        else:
            self.details.set('Connect by Bluetooth or a micro-USB data cable')
        self.warning.set(state.get('error') or '')
        mode = state['mode']
        self.keyboard_button.configure(state='normal' if self.service.desktop_allowed.is_set() else 'disabled')
        if mode != self.last_mode:
            self.auto_button.configure(text=('✓ ' if mode == 'auto' else '') + 'Automatic desktop / game')
            self.game_button.configure(text=('✓ ' if mode == 'gaming' else '') + 'Pause for gaming')
            self.last_mode = mode
        if self.tray_ready:
            self.tray.title = f"{TITLE}: {state['reason']}"[:127]
        self.root.after(16, self.refresh)

    def hide(self):
        if self.tray_ready:
            self.root.withdraw()
        else:
            self.root.iconify()

    def quit(self):
        if self.closing:
            return
        self.closing = True
        self.service.stop()
        self.keyboard.close()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
