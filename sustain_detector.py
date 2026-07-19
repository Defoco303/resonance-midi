from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


class _BitmapInfo(ctypes.Structure):
    _fields_ = (("bmiHeader", _BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 3))


class SustainState(Enum):
    ON = "on"
    OFF = "off"
    ABSENT = "absent"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SustainDetection:
    state: SustainState
    confidence: float = 0.0


def capture_screen_rect(rect: tuple[int, int, int, int]) -> QImage:
    """Capture physical desktop pixels without Qt's DPI coordinate scaling."""
    left, top, width, height = rect
    if width <= 0 or height <= 0:
        return QImage()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HANDLE)
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.BitBlt.argtypes = (
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
    )
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = (
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
    )
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    gdi32.DeleteDC.restype = wintypes.BOOL
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        return QImage()
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height) if memory_dc else 0
    previous = gdi32.SelectObject(memory_dc, bitmap) if bitmap else 0
    try:
        if not memory_dc or not bitmap:
            return QImage()
        # CAPTUREBLT includes layered windows; SRCCOPY copies the visible game
        # surface using the same physical coordinates returned by GetWindowRect.
        if not gdi32.BitBlt(
            memory_dc, 0, 0, width, height, screen_dc, left, top, 0x40CC0020
        ):
            return QImage()
        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # top-down pixels
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0  # BI_RGB
        buffer = (ctypes.c_ubyte * (width * height * 4))()
        if not gdi32.GetDIBits(
            memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0
        ):
            return QImage()
        return QImage(
            buffer, width, height, width * 4, QImage.Format.Format_RGB32
        ).copy()
    finally:
        if previous:
            gdi32.SelectObject(memory_dc, previous)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


def _rect_sum(integral: list[int], stride: int, x: int, y: int, width: int, height: int) -> int:
    right = x + width
    bottom = y + height
    return (
        integral[bottom * stride + right]
        - integral[y * stride + right]
        - integral[bottom * stride + x]
        + integral[y * stride + x]
    )


def detect_sustain_state(source: QImage) -> SustainDetection:
    """Infer the sustain toggle from its high-contrast bar near the piano UI.

    The game renders the bar with a dark background while sustain is off and a
    light background while it is on.  All coordinates and candidate sizes are
    relative to the captured game window, so the same detector can be used for
    windowed, borderless and differently scaled resolutions.
    """
    if source.isNull() or source.width() < 240 or source.height() < 180:
        return SustainDetection(SustainState.UNKNOWN)

    if source.width() > 640:
        height = max(1, round(source.height() * 640 / source.width()))
        source = source.scaled(
            640, height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    image = source.convertToFormat(QImage.Format.Format_Grayscale8)
    width, height = image.width(), image.height()
    bytes_per_line = image.bytesPerLine()
    pixels = bytes(image.constBits())

    stride = width + 1
    integral = [0] * ((height + 1) * stride)
    darkest = 255
    brightest = 0
    for y in range(height):
        row_total = 0
        source_row = y * bytes_per_line
        integral_row = (y + 1) * stride
        previous_row = y * stride
        for x in range(width):
            value = pixels[source_row + x]
            darkest = min(darkest, value)
            brightest = max(brightest, value)
            row_total += value
            integral[integral_row + x + 1] = integral[previous_row + x + 1] + row_total

    # A uniform image generally means that the game surface could not be
    # captured (common with some exclusive-fullscreen configurations).
    if brightest - darkest < 12:
        return SustainDetection(SustainState.UNKNOWN)

    best: tuple[float, float, float] | None = None
    # The label is anchored below the piano at about 60% of the game width.
    # Searching the entire lower UI picked up unrelated bright/dark panels at
    # some aspect ratios, so only a small resolution-relative anchor area is
    # considered.
    x_start = round(width * 0.50)
    x_end = round(width * 0.70)
    y_start = round(height * 0.90)
    y_end = round(height * 0.97)
    x_step = max(2, width // 160)
    y_step = max(1, height // 220)

    for width_fraction in (0.10, 0.12, 0.14):
        candidate_width = max(28, round(width * width_fraction))
        for height_fraction in (0.018, 0.024, 0.030):
            candidate_height = max(7, round(height * height_fraction))
            aspect = candidate_width / candidate_height
            if not 4.0 <= aspect <= 14.0:
                continue
            ring = max(2, round(candidate_height * 0.30))
            for y in range(y_start, max(y_start, y_end - candidate_height) + 1, y_step):
                for x in range(x_start, max(x_start, x_end - candidate_width) + 1, x_step):
                    inner_area = candidate_width * candidate_height
                    inner_sum = _rect_sum(
                        integral, stride, x, y, candidate_width, candidate_height
                    )
                    inner_mean = inner_sum / inner_area

                    outer_x = max(0, x - ring)
                    outer_y = max(0, y - ring)
                    outer_right = min(width, x + candidate_width + ring)
                    outer_bottom = min(height, y + candidate_height + ring)
                    outer_width = outer_right - outer_x
                    outer_height = outer_bottom - outer_y
                    outer_area = outer_width * outer_height - inner_area
                    if outer_area <= 0:
                        continue
                    outer_sum = _rect_sum(
                        integral, stride, outer_x, outer_y, outer_width, outer_height
                    ) - inner_sum
                    outer_mean = outer_sum / outer_area
                    contrast = abs(inner_mean - outer_mean)

                    center_x = (x + candidate_width / 2) / width
                    center_y = (y + candidate_height / 2) / height
                    position_score = (
                        max(0.0, 1.0 - abs(center_x - 0.60) / 0.22) * 8.0
                        + max(0.0, 1.0 - abs(center_y - 0.94) / 0.08) * 8.0
                    )
                    score = contrast + position_score
                    if best is None or score > best[0]:
                        best = (score, contrast, inner_mean)

    if best is None or best[1] < 20.0 or best[0] < 32.0:
        return SustainDetection(SustainState.ABSENT, 0.0 if best is None else best[0])

    score, _, mean = best
    if mean >= 165.0:
        return SustainDetection(SustainState.ON, score)
    if mean <= 115.0:
        return SustainDetection(SustainState.OFF, score)
    return SustainDetection(SustainState.UNKNOWN, score)
