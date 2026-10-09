"""Small, explicit Win32 bindings. All handles use pointer-sized declarations."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys
import winreg

user32 = C.WinDLL('user32', use_last_error=True)
kernel32 = C.WinDLL('kernel32', use_last_error=True)
dwmapi = C.WinDLL('dwmapi', use_last_error=True)
ULONG_PTR = W.WPARAM


def bind(dll, name, args, result):
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, result
    return fn


class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD),
                ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [('uMsg', W.DWORD), ('wParamL', W.WORD), ('wParamH', W.WORD)]


class INPUTUNION(C.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', W.DWORD), ('u', INPUTUNION)]


class MONITORINFO(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]


SendInput = bind(user32, 'SendInput', [W.UINT, C.POINTER(INPUT), C.c_int], W.UINT)
GetForegroundWindow = bind(user32, 'GetForegroundWindow', [], W.HWND)
GetWindowThreadProcessId = bind(user32, 'GetWindowThreadProcessId', [W.HWND, C.POINTER(W.DWORD)], W.DWORD)
GetWindowTextW = bind(user32, 'GetWindowTextW', [W.HWND, W.LPWSTR, C.c_int], C.c_int)
GetClassNameW = bind(user32, 'GetClassNameW', [W.HWND, W.LPWSTR, C.c_int], C.c_int)
GetClientRect = bind(user32, 'GetClientRect', [W.HWND, C.POINTER(W.RECT)], W.BOOL)
ClientToScreen = bind(user32, 'ClientToScreen', [W.HWND, C.POINTER(W.POINT)], W.BOOL)
MonitorFromWindow = bind(user32, 'MonitorFromWindow', [W.HWND, W.DWORD], W.HANDLE)
GetMonitorInfoW = bind(user32, 'GetMonitorInfoW', [W.HANDLE, C.POINTER(MONITORINFO)], W.BOOL)
IsWindowVisible = bind(user32, 'IsWindowVisible', [W.HWND], W.BOOL)
IsIconic = bind(user32, 'IsIconic', [W.HWND], W.BOOL)
OpenProcess = bind(kernel32, 'OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
CloseHandle = bind(kernel32, 'CloseHandle', [W.HANDLE], W.BOOL)
QueryFullProcessImageNameW = bind(kernel32, 'QueryFullProcessImageNameW', [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL)
CreateMutexW = bind(kernel32, 'CreateMutexW', [C.c_void_p, W.BOOL, W.LPCWSTR], W.HANDLE)
FindWindowW = bind(user32, 'FindWindowW', [W.LPCWSTR, W.LPCWSTR], W.HWND)
PostMessageW = bind(user32, 'PostMessageW', [W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL)
ShowWindow = bind(user32, 'ShowWindow', [W.HWND, C.c_int], W.BOOL)
SetForegroundWindow = bind(user32, 'SetForegroundWindow', [W.HWND], W.BOOL)
GetCursorPos = bind(user32, 'GetCursorPos', [C.POINTER(W.POINT)], W.BOOL)
RegisterHotKey = bind(user32, 'RegisterHotKey', [W.HWND, C.c_int, W.UINT, W.UINT], W.BOOL)
UnregisterHotKey = bind(user32, 'UnregisterHotKey', [W.HWND, C.c_int], W.BOOL)
PeekMessageW = bind(user32, 'PeekMessageW', [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT], W.BOOL)
EnumWindowsProc = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
EnumWindows = bind(user32, 'EnumWindows', [EnumWindowsProc, W.LPARAM], W.BOOL)


def dpi_aware():
    try:
        bind(user32, 'SetProcessDpiAwarenessContext', [C.c_void_p], W.BOOL)(C.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def single_instance():
    handle = CreateMutexW(None, False, 'Local\\DS4DesktopAdapter_v1')
    if not handle:
        raise C.WinError(C.get_last_error())
    return handle, C.get_last_error() != 183


def process_path(hwnd):
    pid = W.DWORD()
    GetWindowThreadProcessId(hwnd, C.byref(pid))
    handle = OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ''
    try:
        buf, size = C.create_unicode_buffer(32768), W.DWORD(32768)
        return buf.value if QueryFullProcessImageNameW(handle, 0, buf, C.byref(size)) else ''
    finally:
        CloseHandle(handle)


def window_text(hwnd):
    buf = C.create_unicode_buffer(1024)
    GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def window_class(hwnd):
    buf = C.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def fullscreen(hwnd):
    if not hwnd or IsIconic(hwnd):
        return False
    rect = W.RECT()
    if not GetClientRect(hwnd, C.byref(rect)):
        return False
    point = W.POINT(0, 0)
    if not ClientToScreen(hwnd, C.byref(point)):
        return False
    monitor = MONITORINFO()
    monitor.cbSize = C.sizeof(monitor)
    if not GetMonitorInfoW(MonitorFromWindow(hwnd, 2), C.byref(monitor)):
        return False
    bounds = monitor.rcMonitor
    return (abs(point.x - bounds.left) <= 2 and abs(point.y - bounds.top) <= 2
            and rect.right >= bounds.right - bounds.left - 2
            and rect.bottom >= bounds.bottom - bounds.top - 2)


def monitor_work_area(hwnd=None):
    info = MONITORINFO()
    info.cbSize = C.sizeof(info)
    if GetMonitorInfoW(MonitorFromWindow(hwnd or GetForegroundWindow(), 2), C.byref(info)):
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def visible_apps():
    found = {}
    @EnumWindowsProc
    def visit(hwnd, _):
        if IsWindowVisible(hwnd) and window_text(hwnd):
            path = process_path(hwnd)
            if path:
                name = Path(path).name.lower()
                found[name] = window_text(hwnd)[:85]
        return True
    EnumWindows(visit, 0)
    return sorted(found.items())


def steam_game_roots():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
        roots = [steam / 'steamapps' / 'common']
        libraries = (steam / 'steamapps' / 'libraryfolders.vdf').read_text(encoding='utf-8')
        roots += [Path(p.replace('\\\\', '\\')) / 'steamapps' / 'common'
                  for p in re.findall(r'"path"\s+"([^"]+)"', libraries)]
        return tuple(dict.fromkeys(str(p).lower().replace('/', '\\').rstrip('\\') + '\\' for p in roots))
    except (OSError, ValueError):
        return ()


@dataclass(frozen=True)
class Foreground:
    hwnd: int = 0
    exe: str = ''
    path: str = ''
    full: bool = False
    shell: bool = False


class GameGuard:
    def __init__(self):
        self.roots = steam_game_roots()
        self.cached_hwnd = None
        self.cached_path = ''

    def foreground(self):
        hwnd = GetForegroundWindow()
        if hwnd != self.cached_hwnd:
            self.cached_hwnd, self.cached_path = hwnd, process_path(hwnd) if hwnd else ''
        path = self.cached_path.lower()
        shell = window_class(hwnd) in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd') if hwnd else False
        return Foreground(hwnd or 0, Path(path).name, path, fullscreen(hwnd), shell)

    def reason(self, fg, settings, mode):
        if mode == 'gaming':
            return 'Gaming mode — desktop controls paused'
        if not fg.hwnd:
            return 'Waiting for the desktop'
        if fg.exe in settings['game_apps']:
            return f'Game detected: {fg.exe}'
        if fg.shell or fg.exe in settings['desktop_apps']:
            return ''
        if fg.exe in ('osk.exe', 'tabtip.exe', 'textinputhost.exe', 'ds4desktopadapter.exe'):
            return ''
        if settings['auto_steam_games'] and fg.path.startswith(self.roots):
            return f'Steam game detected: {fg.exe}'
        if settings['auto_fullscreen'] and fg.full:
            return f'Fullscreen app: {fg.exe or "unknown"}'
        return ''


class InputSink:
    def __init__(self):
        self.buttons = set()
        self.keys = set()
        self.error = ''
        self.keyboard_callback = None
        self.hide_keyboard_callback = None

    def send(self, *events):
        if not events:
            return True
        buf = (INPUT * len(events))(*events)
        sent = SendInput(len(events), buf, C.sizeof(INPUT))
        if sent != len(events):
            self.error = 'Windows blocked input. Use the laptop controls for administrator prompts.'
            return False
        self.error = ''
        return True

    def move(self, dx, dy):
        self.send(INPUT(type=0, mi=MOUSEINPUT(dx=dx, dy=dy, dwFlags=0x0001)))

    def scroll(self, ticks):
        self.send(INPUT(type=0, mi=MOUSEINPUT(mouseData=(ticks * 120) & 0xFFFFFFFF, dwFlags=0x0800)))

    def mouse_button(self, button, down):
        flags = {'left': (0x0002, 0x0004), 'right': (0x0008, 0x0010), 'middle': (0x0020, 0x0040)}
        if down:
            self.buttons.add(button)
        sent = self.send(INPUT(type=0, mi=MOUSEINPUT(dwFlags=flags[button][0 if down else 1])))
        if not down and sent:
            self.buttons.discard(button)

    def hotkey(self, keys):
        events = []
        for key in keys:
            self.keys.add(key)
            events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=key, dwFlags=1 if key in (0x25, 0x26, 0x27, 0x28, 0x5B) else 0)))
        for key in reversed(keys):
            events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=key, dwFlags=2 | (1 if key in (0x25, 0x26, 0x27, 0x28, 0x5B) else 0))))
        if self.send(*events):
            self.keys.difference_update(keys)
        else:
            self.release_all()

    def keyboard(self):
        if self.keyboard_callback:
            self.keyboard_callback()
            return
        self.hotkey((0x5B, 0x11, 0x4F))  # Windows + Ctrl + O

    def hide_keyboard(self):
        if self.hide_keyboard_callback:
            self.hide_keyboard_callback()
            return
        hwnd = FindWindowW('OSKMainClass', None)
        if hwnd and IsWindowVisible(hwnd):
            # OSK runs with UIAccess; it can reject WM_CLOSE from a normal process.
            # Windows' accessibility shortcut closes it without requiring elevation.
            self.keyboard()

    def text(self, value):
        events = []
        raw = value.encode('utf-16-le')
        for i in range(0, len(raw), 2):
            code = int.from_bytes(raw[i:i + 2], 'little')
            events.append(INPUT(type=1, ki=KEYBDINPUT(wScan=code, dwFlags=4)))
            events.append(INPUT(type=1, ki=KEYBDINPUT(wScan=code, dwFlags=6)))
        self.send(*events)

    def release_all(self):
        for button in tuple(self.buttons):
            self.mouse_button(button, False)
        for key in tuple(self.keys):
            if self.send(INPUT(type=1, ki=KEYBDINPUT(wVk=key, dwFlags=2 | (1 if key in (0x25, 0x26, 0x27, 0x28, 0x5B) else 0)))):
                self.keys.discard(key)


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            winreg.QueryValueEx(key, 'DS4DesktopAdapter')
            return True
    except OSError:
        return False


def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            if getattr(sys, 'frozen', False):
                command = subprocess.list2cmdline([sys.executable, '--minimized'])
            else:
                pythonw = str(Path(sys.executable).with_name('pythonw.exe'))
                command = subprocess.list2cmdline([pythonw, str(Path(__file__).resolve().parents[1] / 'main.py'), '--minimized'])
            winreg.SetValueEx(key, 'DS4DesktopAdapter', 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, 'DS4DesktopAdapter')
            except FileNotFoundError:
                pass
