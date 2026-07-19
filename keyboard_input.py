"""Windows keyboard injection and target-window helpers."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache

try:
    import pydirectinput
except ImportError:  # Source-only fallback; release builds include it.
    pydirectinput = None
else:
    # PyDirectInput normally sleeps for 0.1 s after every call, which would
    # destroy MIDI timing. The player owns timing and always releases keys.
    pydirectinput.PAUSE = 0.0
    pydirectinput.FAILSAFE = False


user32 = ctypes.windll.user32
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    # INPUT's union must include its largest member (MOUSEINPUT). Defining only
    # KEYBDINPUT makes cbSize 32 instead of 40 on 64-bit Windows, causing
    # SendInput to fail with ERROR_INVALID_PARAMETER (87).
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


# c_void_p intentionally permits both our ABI-correct INPUT and PyDirectInput's
# equivalent Input type. ctypes function prototypes are shared process-wide.
user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


VK_NAMES = {
    "BACKSPACE": 0x08, "TAB": 0x09, "ENTER": 0x0D, "SHIFT": 0x10,
    "CTRL": 0x11, "ALT": 0x12, "ESC": 0x1B, "SPACE": 0x20,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23, "HOME": 0x24,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "INSERT": 0x2D, "DELETE": 0x2E,
    # Use the side-specific virtual keys for the game's toggle controls.
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "RCTRL": 0xA3,
}
VK_NAMES.update({f"F{i}": 0x6F + i for i in range(1, 13)})


def virtual_key(name: str) -> int:
    value = name.strip().upper()
    if value in VK_NAMES:
        return VK_NAMES[value]
    if len(value) == 1:
        result = user32.VkKeyScanW(ord(value))
        if result != -1:
            return result & 0xFF
    raise ValueError(f"未対応のキー名です: {name}")


def _native_send_key(name: str, pressed: bool) -> None:
    vk = virtual_key(name)
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_SCANCODE | (0 if pressed else KEYEVENTF_KEYUP)
    item = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
    if user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError()


DIRECT_KEY_NAMES = {
    "ESC": "esc", "ENTER": "enter", "SHIFT": "shiftleft", "LSHIFT": "shiftleft",
    "RSHIFT": "shiftright",
    "CTRL": "ctrlleft", "LCTRL": "ctrlleft", "ALT": "altleft", "SPACE": "space",
    "BACKSPACE": "backspace", "DELETE": "delete", "INSERT": "insert",
    "PAGEUP": "pageup", "PAGEDOWN": "pagedown", "HOME": "home", "END": "end",
    "LEFT": "left", "RIGHT": "right", "UP": "up", "DOWN": "down",
    # PyDirectInput's names use US positions. These aliases target the same
    # physical scan codes as the labelled JIS keys used by Star Resonance.
    "^": "=", "@": "[", "[": "]",
}


@lru_cache(maxsize=64)
def _direct_key_name(name: str) -> str:
    value = name.strip().upper()
    if value in DIRECT_KEY_NAMES:
        return DIRECT_KEY_NAMES[value]
    if value.startswith("F") and value[1:].isdigit():
        return value.lower()
    if len(value) == 1:
        return value.lower()
    raise ValueError(f"未対応のキー名です: {name}")


def send_key(name: str, pressed: bool) -> None:
    """Send through the same DirectInput-oriented path as fishing_macro."""
    if pydirectinput is None:
        _native_send_key(name, pressed)
        return
    direct_name = _direct_key_name(name)
    action = pydirectinput.keyDown if pressed else pydirectinput.keyUp
    if action(direct_name, _pause=False) is not True:
        raise OSError(f"PyDirectInputでキーを送信できません: {name}")


def input_backend_name() -> str:
    return "PyDirectInput（ゲーム向け）" if pydirectinput is not None else "Windows SendInput"


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str


def list_windows() -> list[WindowInfo]:
    windows: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if title:
                windows.append(WindowInfo(int(hwnd), title))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return sorted(windows, key=lambda item: item.title.casefold())


def focus_window(hwnd: int) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    return bool(user32.SetForegroundWindow(hwnd))


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return the visible window rectangle in virtual-screen coordinates."""
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    return rect.left, rect.top, width, height
