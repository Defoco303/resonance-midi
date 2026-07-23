from __future__ import annotations

import math
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import QByteArray, QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedLayout,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config_store import default_mapping, load_config, mapping_for_game_octave, save_config
from instruments import (
    DEFAULT_INSTRUMENT,
    DEFAULT_UNLOCK_STAGE,
    INSTRUMENTS,
    instrument_profile,
)
from keyboard_input import (
    WindowInfo,
    allow_drag_drop,
    focus_window,
    foreground_window,
    list_windows,
    send_key,
    window_rect,
)
from midi_parser import MidiError, MidiNote, MidiSong, load_midi, note_name
from midi_writer import write_midi
from player import MidiPlayer
from sustain_detector import SustainState, capture_screen_rect, detect_sustain_state


GAME_WINDOW_TITLE = "ブループロトコル：スターレゾナンス"
SUSTAIN_HELP = (
    "通常は、音符の長さ（4分・8分音符など）ぶんキーを押し続けます。\n"
    "ただし音域の切り替えが激しい曲では、音を伸ばしきれず、"
    "プツプツと途切れて聞こえることがあります。"
    "その場合はゲーム側のサステインをオンにすると、キーを離しても音が伸びて"
    "途切れが目立ちません。"
)
WHITE = "#ffffff"
ACCENT = "#bdf7ff"
ICON_BLUE = WHITE
PLAY_BLUE = "#147bd1"
STOP_RED = "#c83d45"


def format_time(value: float) -> str:
    total = max(0, int(value))
    return f"{total // 60}:{total % 60:02d}"


def svg_icon(svg: str, size: int) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def gear_icon(size: int = 18) -> QIcon:
    # Same Feather-style path used by resonance-chat.
    return svg_icon(f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
         stroke="{ICON_BLUE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>""", size)


def eighth_note_icon(size: int = 18) -> QIcon:
    """A single eighth note. The head is slanted the way engraving draws it."""
    return svg_icon(f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
         stroke="{ICON_BLUE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <ellipse cx="8.6" cy="17.6" rx="4.3" ry="3.1" fill="{ICON_BLUE}" stroke="none"
               transform="rotate(-20 8.6 17.6)"/>
      <path d="M12.7 16.6V4.2"/>
      <path d="M12.7 4.6c3.4 1.2 5.2 3.2 5 6.4"/>
    </svg>""", size)


def simple_icon(kind: str, color: str = WHITE, size: int = 18) -> QIcon:
    shapes = {
        "close": '<path d="M6 6l12 12M18 6L6 18"/>',
        "play": f'<path fill="{color}" stroke="none" d="M8 5l11 7-11 7z"/>',
        "stop": f'<rect fill="{color}" stroke="none" x="7" y="7" width="10" height="10"/>',
        "restart": '<path d="M6 5v14M9 12l9-6v12z"/>',
        "refresh": '<path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 7l-2 4M5.5 15A7 7 0 0 0 18 17l2-4"/>',
        "up": f'<path fill="{color}" stroke="none" d="M6 15l6-7 6 7z"/>',
        "down": f'<path fill="{color}" stroke="none" d="M6 9l6 7 6-7z"/>',
        "list": '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
        "magnet": '<path d="M7 20v-8a5 5 0 0 1 10 0v8"/><path d="M4.5 20h5M14.5 20h5"/>',
        "prev": f'<path fill="{color}" stroke="none" d="M7 6h2v12H7z"/><path fill="{color}" stroke="none" d="M20 6v12l-9-6z"/>',
        "next": f'<path fill="{color}" stroke="none" d="M15 6h2v12h-2z"/><path fill="{color}" stroke="none" d="M4 6v12l9-6z"/>',
        "shuffle": '<path d="M16 3h5v5"/><path d="M4 20 21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/>',
        "repeat": '<path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
        "repeat_one": ('<path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>'
                       '<path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>'
                       f'<text x="12" y="15.5" font-size="9" font-weight="700" fill="{color}" '
                       'stroke="none" text-anchor="middle" font-family="sans-serif">1</text>'),
    }
    return svg_icon(f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
         stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      {shapes[kind]}
    </svg>""", size)


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setToolTip(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self.update()

    def text(self) -> str:
        return self._full_text

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        metrics = QFontMetrics(self.font())
        value = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(self.alignment()), value)


class MidiSpectrumWidget(QWidget):
    """Lightweight MIDI-driven spectrum-like display.

    This deliberately visualizes the notes prepared by MidiPlayer instead of
    capturing game audio. All animation runs on the Qt thread at 20 fps.
    """

    BAR_COUNT = 44
    FIRST_NOTE = 21   # A0
    LAST_NOTE = 108   # C8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setToolTip("MIDI音符から生成した疑似スペクトラム")
        self._events: list[tuple[float, int, int, float]] = []
        self._event_index = 0
        self._last_position = 0.0
        self._playing = False
        self._energy = [0.0] * self.BAR_COUNT
        self._impulse = [0.0] * self.BAR_COUNT
        self._levels = [0.0] * self.BAR_COUNT
        self._peaks = [0.0] * self.BAR_COUNT
        self._peak_hold = [0] * self.BAR_COUNT
        self._colors = [
            self._mix_color(QColor(70, 190, 216), QColor(218, 224, 91),
                            index / max(1, self.BAR_COUNT - 1))
            for index in range(self.BAR_COUNT)
        ]
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._advance_frame)

    @staticmethod
    def _mix_color(first: QColor, second: QColor, amount: float) -> QColor:
        inverse = 1.0 - amount
        return QColor(
            round(first.red() * inverse + second.red() * amount),
            round(first.green() * inverse + second.green() * amount),
            round(first.blue() * inverse + second.blue() * amount),
            132,
        )

    def _band_for(self, note: int) -> int:
        # A0-C8 is exactly 88 notes: pair adjacent semitones into 44 bars.
        return max(0, min(self.BAR_COUNT - 1, (note - self.FIRST_NOTE) // 2))

    def set_notes(self, notes: list[MidiNote]) -> None:
        events: list[tuple[float, int, int, float]] = []
        for note in notes:
            fundamental = max(0.12, min(1.0, note.velocity / 127.0))
            # A small harmonic stack makes sparse MIDI notes read like a real
            # spectrum without capturing audio or performing an FFT.
            for offset, weight in ((0, 1.0), (12, 0.34), (19, 0.18)):
                harmonic = note.note + offset
                if harmonic > self.LAST_NOTE:
                    continue
                band = self._band_for(harmonic)
                strength = fundamental * weight
                events.append((note.start, 1, band, strength))
                events.append((note.end, -1, band, strength))
        # Releases precede attacks at the same timestamp so repeated notes flash
        # as distinct hits instead of momentarily doubling their active energy.
        self._events = sorted(events, key=lambda item: (item[0], item[1]))
        self._event_index = 0
        self._last_position = 0.0
        self._playing = False
        self._energy = [0.0] * self.BAR_COUNT
        self._impulse = [0.0] * self.BAR_COUNT
        self._levels = [0.0] * self.BAR_COUNT
        self._peaks = [0.0] * self.BAR_COUNT
        self._peak_hold = [0] * self.BAR_COUNT
        self._timer.stop()
        self.update()

    def set_position(self, position: float, playing: bool) -> None:
        position = max(0.0, float(position))
        if playing:
            if position < self._last_position or position - self._last_position > 0.20:
                self._rebuild_energy(position)
            else:
                self._consume_until(position, flash=True)
            self._playing = True
            if self.isVisible() and not self.window().isMinimized() and not self._timer.isActive():
                self._timer.start()
        else:
            self._playing = False
            self._energy = [0.0] * self.BAR_COUNT
            self._impulse = [0.0] * self.BAR_COUNT
            if position <= 0.0:
                self._event_index = 0
                self._last_position = 0.0
            else:
                self._rebuild_energy(position)
                self._energy = [0.0] * self.BAR_COUNT
            if (self.isVisible() and not self.window().isMinimized()
                    and any(level > 0.01 for level in self._levels)
                    and not self._timer.isActive()):
                self._timer.start()
        self._last_position = position

    def _consume_until(self, position: float, flash: bool) -> None:
        while self._event_index < len(self._events):
            event_time, direction, band, strength = self._events[self._event_index]
            if event_time > position:
                break
            self._energy[band] = max(0.0, self._energy[band] + direction * strength)
            if direction > 0 and flash:
                self._impulse[band] = max(self._impulse[band], strength)
            self._event_index += 1

    def _rebuild_energy(self, position: float) -> None:
        self._event_index = 0
        self._energy = [0.0] * self.BAR_COUNT
        self._impulse = [0.0] * self.BAR_COUNT
        self._consume_until(position, flash=False)

    def _advance_frame(self) -> None:
        if not self.isVisible() or self.window().isMinimized():
            self._timer.stop()
            return
        visible = False
        for index in range(self.BAR_COUNT):
            active = min(1.0, math.sqrt(self._energy[index] / 1.7))
            target = max(active, self._impulse[index])
            level = self._levels[index]
            if target >= level:
                level += (target - level) * 0.82
            else:
                level = max(target, level * 0.78)
            self._levels[index] = 0.0 if level < 0.006 else level
            self._impulse[index] *= 0.58

            if level >= self._peaks[index]:
                self._peaks[index] = level
                self._peak_hold[index] = 3
            elif self._peak_hold[index] > 0:
                self._peak_hold[index] -= 1
            else:
                self._peaks[index] = max(level, self._peaks[index] - 0.055)
            visible = visible or level > 0.006 or self._peaks[index] > 0.006

        self.update()
        if not self._playing and not visible:
            self._timer.stop()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        graph_top = 2
        graph_bottom = max(graph_top + 1, self.height() - 2)
        graph_height = graph_bottom - graph_top
        graph_width = max(1, self.width() - 2)

        cell_width = graph_width / self.BAR_COUNT
        gap = max(1, round(cell_width * 0.22))
        for index, level in enumerate(self._levels):
            left = 1 + round(index * cell_width) + gap // 2
            right = 1 + round((index + 1) * cell_width) - (gap - gap // 2)
            width = max(1, right - left)
            if level <= 0.0:
                continue
            height = max(1, round(level * graph_height))
            painter.fillRect(left, graph_bottom - height, width, height, self._colors[index])

            peak = self._peaks[index]
            if peak > 0.02:
                peak_y = graph_bottom - round(peak * graph_height)
                peak_color = QColor(self._colors[index])
                peak_color.setAlpha(190)
                painter.fillRect(left, max(graph_top, peak_y), width, 1, peak_color)

class DragBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = QPoint()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._offset)
            anchor = getattr(self.window(), "anchor_options", None)
            if anchor is not None:
                anchor()
            event.accept()


class ArrowSpinBox(QWidget):
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.spin = QSpinBox()
        self.spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin.valueChanged.connect(self.valueChanged.emit)
        layout.addWidget(self.spin, 1)
        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(0)
        up = QToolButton()
        down = QToolButton()
        for button, icon in ((up, simple_icon("up", WHITE, 10)), (down, simple_icon("down", WHITE, 10))):
            button.setObjectName("stepButton")
            button.setIcon(icon)
            button.setIconSize(QPixmap(icon.pixmap(10, 10)).size())
            button.setFixedSize(26, 15)
            buttons.addWidget(button)
        up.clicked.connect(self.spin.stepUp)
        down.clicked.connect(self.spin.stepDown)
        layout.addLayout(buttons)

    def setRange(self, low: int, high: int) -> None:
        self.spin.setRange(low, high)

    def setValue(self, value: int) -> None:
        self.spin.setValue(value)

    def value(self) -> int:
        return self.spin.value()


class SeekSlider(QSlider):
    jumped = Signal(int)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option,
            QStyle.SubControl.SC_SliderHandle, self,
        )
        if handle.contains(event.position().toPoint()):
            super().mousePressEvent(event)
            return
        value = QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), round(event.position().x()), max(1, self.width())
        )
        self.setValue(value)
        self.jumped.emit(value)
        event.accept()


class PlayerBridge(QObject):
    position = Signal(float, str)
    error = Signal(str)


class AlertDialog(QDialog):
    """Dark, red-framed modal used for warnings and playback errors."""

    def __init__(self, parent: QWidget, title: str, message: str,
                 confirm: bool = False, ok_text: str = "OK", kind: str = "warning"):
        super().__init__(
            parent,
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(title)
        scale = max(0.5, min(2.0, float(getattr(parent, "ui_scale", 1.0))))
        px = lambda value: max(1, round(value * scale))
        self.setFixedWidth(px(500))

        # "info" reuses the same dark modal in the app's blue instead of red.
        # The OK button is outlined in the frame colour and the close button is
        # neutral, so only the frame/divider colour differs by kind.
        if kind == "info":
            frame = "#2f8fb0"
            divider = "rgba(47, 143, 176, 150)"
        else:
            frame = "#e0525a"
            divider = "rgba(224, 82, 90, 150)"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("alertShell")
        outer.addWidget(shell)

        body = QVBoxLayout(shell)
        body.setContentsMargins(px(16), 0, px(16), px(10))
        body.setSpacing(px(6))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("alertTitle")
        header.addWidget(title_label)
        header.addStretch()
        close = QToolButton()
        close.setIcon(simple_icon("close", WHITE, 15))
        close.setIconSize(QSize(px(20), px(20)))
        close.setFixedSize(px(32), px(30))
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # A cascaded stylesheet does not reach these buttons under Fusion, so the
        # look is set directly on each one (matches the app's iconButton).
        close.setStyleSheet(
            "QToolButton { background: transparent; border: none; }"
            "QToolButton:hover { background-color: rgba(70, 90, 110, 190); }"
        )
        close.clicked.connect(self.reject)
        header.addWidget(close)
        body.addLayout(header)

        divider = QFrame()
        divider.setObjectName("alertDivider")
        divider.setFixedHeight(px(1))
        body.addWidget(divider)

        message_label = QLabel(message)
        message_label.setObjectName("alertMessage")
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        # A word-wrapped QLabel over-reports its sizeHint height and centres the
        # text, leaving big gaps. Fix it to the actual wrapped text height.
        msg_font = QFont("Yu Gothic UI")
        msg_font.setPixelSize(px(13))
        message_label.setFont(msg_font)
        usable = px(500) - 2 * px(16)
        text_height = QFontMetrics(msg_font).boundingRect(
            0, 0, usable, 100000, int(Qt.TextFlag.TextWordWrap), message).height()
        message_label.setFixedHeight(text_height)
        body.addWidget(message_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        if confirm:
            cancel = QPushButton("キャンセル")
            cancel.setFixedSize(px(104), px(32))
            cancel.setAutoDefault(False)
            cancel.setStyleSheet(
                f"QPushButton {{ color: {WHITE}; background-color: #242a31;"
                f" border: {px(1)}px solid #4a535d; font-weight: 700; }}"
                "QPushButton:hover { background-color: #39434e; }"
            )
            cancel.clicked.connect(self.reject)
            buttons.addWidget(cancel)
        # Outlined "just border + text" button (no fill). Set directly: the
        # dialog's cascaded stylesheet does not reach it under Fusion.
        ok = QPushButton(ok_text)
        ok.setFixedSize(px(104), px(32))
        ok.setAutoDefault(False)
        ok.setDefault(False)
        ok.setStyleSheet(
            f"QPushButton {{ color: {WHITE}; background: transparent;"
            f" border: {px(1)}px solid {frame}; font-weight: 700; }}"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 28); }"
            "QPushButton:pressed { background-color: rgba(255, 255, 255, 45); }"
        )
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        body.addLayout(buttons)

        self.setStyleSheet(f"""
            QDialog {{ background: transparent; }}
            QFrame#alertShell {{
                background-color: rgba(8, 12, 17, 248);
                border: {px(2)}px solid {frame};
            }}
            QLabel {{
                color: {WHITE};
                background: transparent;
                border: none;
                font-family: "Yu Gothic UI";
                font-size: {px(13)}px;
            }}
            QLabel#alertTitle {{
                color: {WHITE};
                font-size: {px(15)}px;
                font-weight: 700;
            }}
            QLabel#alertMessage {{ color: {WHITE}; }}
            QFrame#alertDivider {{ background-color: {divider}; border: none; }}
            QPushButton {{ font-family: "Yu Gothic UI"; font-size: {px(13)}px; }}
        """)
        self.adjustSize()
        # Fit the content height (buttons are styled directly, above).
        self.setFixedHeight(self.sizeHint().height())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parentWidget() is not None:
            parent_rect = self.parentWidget().frameGeometry()
            self.move(parent_rect.center() - self.rect().center())


class PopoutWindow(QWidget):
    """Shared chrome for the panels that hang off the main window.

    Only one of them is ever visible; the owner closes the other one first.
    """

    closed = Signal()
    heading = ""
    resizable = False
    min_size = (380, 150)

    def __init__(self, owner: "ResonanceMidiWindow", width: int, height: int):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(f"Resonance MIDI Player - {self.heading.title()}")
        if self.resizable:
            # A free-floating, user-resizable panel (see PlaylistWindow); leaving
            # the size unfixed lets scale_widget_tree skip its setFixedSize step.
            self.setMinimumSize(*self.min_size)
            self.resize(width, height)
        else:
            self.setFixedSize(width, height)
        self._build(self._build_chrome())
        self.owner.scale_widget_tree(self)
        self.owner.apply_background_style(self)

    def _add_header_extras(self, header_layout: QHBoxLayout) -> None:
        """Hook for subclasses to add buttons left of the close button."""

    def _build_chrome(self) -> QVBoxLayout:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        accent = QFrame()
        accent.setObjectName("accentBar")
        accent.setFixedWidth(4)
        outer.addWidget(accent)
        shell = QFrame()
        shell.setObjectName("shell")
        outer.addWidget(shell, 1)
        body = QVBoxLayout(shell)
        body.setContentsMargins(8, 0, 8, 8)
        body.setSpacing(0)

        header = DragBar()
        header.setObjectName("header")
        header.setFixedHeight(32)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 0, 0)
        title = QLabel(self.heading)
        title.setObjectName("windowTitle")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._add_header_extras(header_layout)
        close = self.owner.icon_button(simple_icon("close", WHITE, 15), "閉じる", 32)
        # Holding × to close must not trip the focus-stop while the button is
        # down (the panel is foreground during the hold); _popout_closing takes
        # over once it actually closes. Only the × does this — opening a panel
        # or touching its other controls still stops playback (option A).
        close.pressed.connect(lambda: setattr(self.owner, "_suppress_focus_stop", True))
        close.released.connect(lambda: setattr(self.owner, "_suppress_focus_stop", False))
        close.clicked.connect(self.close)
        header_layout.addWidget(close)
        body.addWidget(header)
        return body

    def _build(self, body: QVBoxLayout) -> None:
        raise NotImplementedError

    def _form_row(self, layout: QVBoxLayout, label: str, control: QWidget) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(8)
        caption = QLabel(label)
        row.addWidget(caption)
        row.addStretch()
        control.setMinimumWidth(215)
        row.addWidget(control)
        layout.addLayout(row)
        return caption

    def show_front(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        self.owner.save()
        self.closed.emit()
        super().closeEvent(event)


class OptionsWindow(PopoutWindow):
    heading = "OPTIONS"

    def __init__(self, owner: "ResonanceMidiWindow"):
        super().__init__(owner, 650, 228)

    def _build(self, body: QVBoxLayout) -> None:
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(6)
        play_panel = self.owner.panel()
        view_panel = self.owner.panel()
        columns.addWidget(play_panel, 3)
        columns.addWidget(view_panel, 2)
        body.addLayout(columns, 1)
        self._build_play_settings(play_panel)
        self._build_view_settings(view_panel)

    def _build_play_settings(self, panel: QFrame) -> None:
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        heading = QLabel("再生設定")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        speed = QComboBox()
        speed.addItems(["0.25", "0.5", "0.75", "1.0", "1.25", "1.5", "2.0"])
        speed.setCurrentText(str(self.owner.speed))
        speed.currentTextChanged.connect(lambda text: self.owner.update_setting("speed", float(text)))
        self._form_row(layout, "再生速度", speed)

        transpose = ArrowSpinBox()
        transpose.setRange(-36, 36)
        transpose.setValue(self.owner.transpose)
        transpose.valueChanged.connect(lambda value: self.owner.update_setting("transpose", value))
        self._form_row(layout, "移調（半音）", transpose)

        switch = ArrowSpinBox()
        switch.setRange(0, 100)
        switch.setValue(self.owner.octave_switch_ms)
        switch.valueChanged.connect(lambda value: self.owner.update_setting("octave_switch_ms", value))
        self._form_row(layout, "音域切替待機 ms", switch)
        layout.addStretch()

    def _build_view_settings(self, panel: QFrame) -> None:
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(7)
        heading = QLabel("表示・開始設定")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        countdown_row = QHBoxLayout()
        countdown_row.addWidget(QLabel("開始カウントダウン"))
        countdown_row.addStretch()
        countdown = ArrowSpinBox()
        countdown.setRange(0, 10)
        countdown.setValue(self.owner.countdown)
        countdown.valueChanged.connect(lambda value: self.owner.update_setting("countdown", value))
        countdown_row.addWidget(countdown)
        layout.addLayout(countdown_row)

        top = QCheckBox("常に手前に表示")
        top.setChecked(self.owner.topmost)
        top.toggled.connect(self.owner.set_topmost)
        layout.addWidget(top)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("背景の透明度"))
        opacity_row.addStretch()
        self.opacity_value = QLabel(f"{round(self.owner.opacity * 100)}%")
        self.opacity_value.setObjectName("strongLabel")
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)
        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(50, 100)
        opacity.setValue(round(self.owner.opacity * 100))
        opacity.valueChanged.connect(self._opacity_changed)
        opacity.sliderReleased.connect(self.owner.save)
        layout.addWidget(opacity)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("UIの大きさ"))
        scale_row.addStretch()
        self.scale_value = QLabel(f"{self.owner.ui_scale:.1f}x")
        self.scale_value.setObjectName("strongLabel")
        scale_row.addWidget(self.scale_value)
        layout.addLayout(scale_row)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(5, 20)
        self.scale_slider.setSingleStep(1)
        self.scale_slider.setPageStep(1)
        self.scale_slider.setTickInterval(1)
        self.scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.scale_slider.setValue(round(self.owner.ui_scale * 10))
        self.scale_slider.valueChanged.connect(
            lambda value: self.scale_value.setText(f"{value / 10:.1f}x")
        )
        self.scale_slider.sliderReleased.connect(
            lambda: self.owner.set_ui_scale(self.scale_slider.value() / 10)
        )
        layout.addWidget(self.scale_slider)
        layout.addStretch()

    def _opacity_changed(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self.owner.opacity = value / 100.0
        self.owner.config["opacity"] = self.owner.opacity
        self.owner.apply_background_style(self.owner)
        self.owner.apply_background_style(self)


class InstrumentWindow(PopoutWindow):
    heading = "INSTRUMENTS SETTING"

    def __init__(self, owner: "ResonanceMidiWindow"):
        super().__init__(owner, 650, 176)

    def _build(self, body: QVBoxLayout) -> None:
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(6)
        instrument_panel = self.owner.panel()
        correction_panel = self.owner.panel()
        # The correction panel is wider because the unlock-stage labels are long.
        columns.addWidget(instrument_panel, 2)
        columns.addWidget(correction_panel, 3)
        body.addLayout(columns, 1)
        self._build_instrument_panel(instrument_panel)
        self._build_correction_panel(correction_panel)
        # ResonanceMidiWindow.export_audible_midi() and midi_writer are kept
        # deliberately: the export is still the only way to audition the
        # correction away from the game, it just has no button right now.
        self._reload_stages()

    def _build_instrument_panel(self, panel: QFrame) -> None:
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        heading = QLabel("楽器")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        self.instrument = QComboBox()
        for index, profile in enumerate(INSTRUMENTS):
            self.instrument.addItem(profile.label, profile.key)
            if not profile.selectable:
                # Kept visible so the unsupported instruments are discoverable,
                # but unselectable until their behaviour has been verified.
                item = self.instrument.model().item(index)
                item.setEnabled(False)
                item.setToolTip(profile.note)
        self.instrument.setCurrentIndex(
            max(0, self.instrument.findData(self.owner.instrument))
        )
        self.instrument.currentIndexChanged.connect(self._instrument_changed)
        layout.addWidget(self.instrument)

        # Both are instrument-specific and get greyed out for drums (drums are
        # the ch.10 track itself and have no sustain).
        self.ignore_drums_check = QCheckBox("ドラム（MIDI ch.10）を除外")
        self.ignore_drums_check.setChecked(self.owner.ignore_drums)
        self.ignore_drums_check.toggled.connect(
            lambda value: self.owner.update_setting("ignore_drums", value)
        )
        layout.addWidget(self.ignore_drums_check)
        self.sustain_check = QCheckBox("サステイン状態のチェック")
        self.sustain_check.setChecked(self.owner.sustain_check)
        self.sustain_check.toggled.connect(
            lambda value: self.owner.update_setting("check_sustain_state", value)
        )
        layout.addWidget(self.sustain_check)
        # A blue link that opens the explanation in a popup (hover tooltips were
        # too easy to miss).
        self.sustain_help = QLabel(
            f'<a href="#" style="color:{ACCENT}; text-decoration:underline;">'
            "サステインペダルのオンオフについて</a>"
        )
        self.sustain_help.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.sustain_help.linkActivated.connect(
            lambda: self.owner.show_info("サステインペダルのオンオフについて", SUSTAIN_HELP)
        )
        layout.addWidget(self.sustain_help)
        # Opacity effects so the whole checkbox (box + label), not just the text,
        # dims when it is greyed out for drums.
        self._drum_dim_effects = []
        for checkbox in (self.ignore_drums_check, self.sustain_check):
            effect = QGraphicsOpacityEffect(checkbox)
            checkbox.setGraphicsEffect(effect)
            self._drum_dim_effects.append(effect)
        layout.addStretch()

    def _build_correction_panel(self, panel: QFrame) -> None:
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        heading = QLabel("音域補正（ベータ）")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        self.correction = QCheckBox("未解放の音域の音を、解放済みの音域へ補正する")
        self.correction.setChecked(self.owner.range_correction)
        self.correction.toggled.connect(self._correction_toggled)
        layout.addWidget(self.correction)

        self.stage = QComboBox()
        self.stage.currentIndexChanged.connect(self._stage_changed)
        self.stage_caption = self._form_row(layout, "解放段階", self.stage)
        layout.addStretch()

    def _correction_toggled(self, value: bool) -> None:
        self.owner.update_setting("range_correction", value)
        self._apply_enabled()

    def _apply_enabled(self) -> None:
        """Grey out the range settings while the correction is switched off."""
        on = self.correction.isChecked()
        profile = instrument_profile(self.owner.instrument)
        # The instrument choice stays usable regardless of correction, but the
        # unlock stage is gated by the correction checkbox for every instrument
        # (drums included) so the panel behaves consistently.
        self.stage_caption.setEnabled(on)
        self.stage.setEnabled(on and len(profile.stages) > 1)
        # Drums have no sustain and are the ch.10 track itself, so neither toggle
        # applies while drums are selected (playback ignores them regardless).
        drums = profile.key == "drums"
        self.ignore_drums_check.setEnabled(not drums)
        self.sustain_check.setEnabled(not drums)
        for effect in self._drum_dim_effects:
            effect.setOpacity(0.4 if drums else 1.0)

    def _reload_stages(self) -> None:
        profile = instrument_profile(self.owner.instrument)
        self.stage.blockSignals(True)
        self.stage.clear()
        for step in profile.stages:
            self.stage.addItem(step.label)
        self.stage.setCurrentIndex(profile.clamp_stage(self.owner.unlock_stage))
        self.stage.blockSignals(False)
        self._apply_enabled()

    def _instrument_changed(self, index: int) -> None:
        key = self.instrument.itemData(index)
        self.owner.update_setting("instrument", key)
        # Guitar and bass ring on their own; the game sustain only muddies them,
        # so default it off when the user picks one (still toggleable).
        if key in ("guitar", "bass") and self.sustain_check.isChecked():
            self.sustain_check.setChecked(False)  # fires toggled -> update_setting
        self._reload_stages()

    def _stage_changed(self, index: int) -> None:
        self.owner.update_setting("unlock_stage", index)


DIM = "#8a949e"  # inactive icon tint for the shuffle/repeat toggles

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_DURATION = Qt.ItemDataRole.UserRole + 1
ROLE_PLAYING = Qt.ItemDataRole.UserRole + 2


class PlaylistDelegate(QStyledItemDelegate):
    """Draws one row as: No. (left)  filename (middle, elided)  m:ss (right)."""

    def __init__(self, owner: "ResonanceMidiWindow", parent=None):
        super().__init__(parent)
        self.owner = owner

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, max(1, round(26 * self.owner.ui_scale)))

    def paint(self, painter, option, index) -> None:
        px = lambda value: max(1, round(value * self.owner.ui_scale))
        rect = option.rect
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor("#29465f"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(70, 90, 110, 90))
        playing = bool(index.data(ROLE_PLAYING))
        font = QFont(option.font)
        font.setBold(playing)
        painter.setFont(font)
        painter.setPen(QColor(ACCENT) if playing else QColor(WHITE))
        metrics = QFontMetrics(font)
        pad, no_w, dur_w, gap = px(8), px(30), px(46), px(8)
        left = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        right = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        no_rect = QRect(rect.left() + pad, rect.top(), no_w, rect.height())
        painter.drawText(no_rect, left, str(index.row() + 1))
        duration = index.data(ROLE_DURATION)
        dur_rect = QRect(rect.right() - pad - dur_w, rect.top(), dur_w, rect.height())
        painter.drawText(dur_rect, right, format_time(float(duration)) if duration else "--:--")
        name_left = no_rect.right() + gap
        name_rect = QRect(name_left, rect.top(), max(0, dur_rect.left() - gap - name_left), rect.height())
        name = ("▶  " if playing else "") + Path(index.data(ROLE_PATH)).stem
        painter.drawText(name_rect, left,
                         metrics.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width()))
        painter.restore()


class PlaylistList(QListWidget):
    """Multi-select drag-reorder list.

    Reports internal reorders and Delete presses, and accepts MIDI files or
    folders dragged in from Explorer (non-MIDI is silently ignored; a dropped
    folder contributes only its direct .mid/.midi children, not recursively).
    """

    reordered = Signal()
    removed = Signal()
    filesDropped = Signal(list)

    @staticmethod
    def _collect(urls) -> list[str]:
        result: list[str] = []
        for url in urls:
            path = Path(url.toLocalFile())
            if path.is_dir():
                result.extend(sorted(
                    str(child) for child in path.iterdir()
                    if child.is_file() and child.suffix.lower() in (".mid", ".midi")))
            elif path.is_file() and path.suffix.lower() in (".mid", ".midi"):
                result.append(str(path))
        return result

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = self._collect(event.mimeData().urls())
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        self.reordered.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selectedItems():
            self.removed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PlaylistWindow(PopoutWindow):
    heading = "PLAYLIST"
    resizable = True
    min_size = (430, 190)

    def __init__(self, owner: "ResonanceMidiWindow"):
        super().__init__(owner, 650, 310)

    def _add_header_extras(self, header_layout: QHBoxLayout) -> None:
        self.reset_button = self.owner.icon_button(
            simple_icon("magnet", WHITE, 16), "初期の位置・サイズに戻す", 32)
        self.reset_button.clicked.connect(self._reset_geometry)
        header_layout.addWidget(self.reset_button)

    def _build(self, body: QVBoxLayout) -> None:
        self.setAcceptDrops(True)  # accept file drops anywhere on the window
        panel = self.owner.panel()
        body.addWidget(panel, 1)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self.list = PlaylistList()
        self.list.setObjectName("playlist")
        self.list.setItemDelegate(PlaylistDelegate(self.owner, self.list))
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setAcceptDrops(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.itemDoubleClicked.connect(self._play_item)
        self.list.reordered.connect(self._reordered)
        self.list.removed.connect(self._remove_selected)
        self.list.filesDropped.connect(self.owner.add_to_playlist)
        self.list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list, 1)

        transport = QHBoxLayout()
        transport.setSpacing(4)
        # Left: ＋FILE, same size as the main window's ＋MIDI button.
        add_file = QPushButton("＋ FILE")
        add_file.setObjectName("midiButton")
        add_file.setFixedSize(81, 34)
        add_file.setToolTip("MIDIファイルを追加（ダイアログで Shift/Ctrl 複数選択可）")
        add_file.clicked.connect(self._add_files)
        transport.addWidget(add_file)
        transport.addStretch()
        # Center: the four transport icons.
        self.shuffle_button = self.owner.icon_button(simple_icon("shuffle", WHITE, 18), "シャッフル", 34)
        self.shuffle_button.clicked.connect(self._toggle_shuffle)
        self.prev_button = self.owner.icon_button(simple_icon("prev", WHITE, 18), "前の曲", 34)
        self.prev_button.clicked.connect(lambda: self.owner.playlist_step(-1))
        self.next_button = self.owner.icon_button(simple_icon("next", WHITE, 18), "次の曲", 34)
        self.next_button.clicked.connect(lambda: self.owner.playlist_step(1))
        self.repeat_button = self.owner.icon_button(simple_icon("repeat", WHITE, 18), "リピート", 34)
        self.repeat_button.clicked.connect(self._cycle_repeat)
        for widget in (self.shuffle_button, self.prev_button, self.next_button, self.repeat_button):
            transport.addWidget(widget)
        transport.addStretch()
        # Right: the between-song gap.
        transport.addWidget(QLabel("曲間"))
        self.gap_spin = ArrowSpinBox()
        self.gap_spin.setRange(0, 10)
        self.gap_spin.setValue(self.owner.playlist_gap)
        self.gap_spin.setFixedWidth(72)
        self.gap_spin.valueChanged.connect(lambda value: self.owner.update_setting("playlist_gap", value))
        transport.addWidget(self.gap_spin)
        transport.addWidget(QLabel("秒"))
        transport.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        layout.addLayout(transport)

        self.refresh_rows()
        self.refresh_modes()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = PlaylistList._collect(event.mimeData().urls())
            if paths:
                self.owner.add_to_playlist(paths)
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        # Remember position and size for the rest of this session (not saved to
        # disk: every launch starts back at the default geometry).
        self.owner._playlist_geometry = QRect(self.geometry())
        super().closeEvent(event)

    def _reset_geometry(self) -> None:
        self.owner._playlist_geometry = None
        self.owner._apply_playlist_default_geometry(self)

    # --- list <-> owner plumbing --------------------------------------------
    def _paths(self) -> list[str]:
        return [self.list.item(i).data(ROLE_PATH) for i in range(self.list.count())]

    def refresh_rows(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for path in self.owner.playlist:
            item = QListWidgetItem()
            item.setData(ROLE_PATH, path)
            item.setData(ROLE_DURATION, self.owner._duration_for(path))
            item.setToolTip(path)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.mark_current(self.owner.playlist_index)

    def mark_current(self, index: int) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setData(ROLE_PLAYING, i == index)
        self.list.viewport().update()

    def refresh_modes(self) -> None:
        on = self.owner.playlist_shuffle
        self.shuffle_button.setIcon(simple_icon("shuffle", ACCENT if on else DIM, 18))
        mode = self.owner.playlist_repeat
        color = DIM if mode == "off" else ACCENT
        self.repeat_button.setIcon(simple_icon("repeat_one" if mode == "one" else "repeat", color, 18))
        self.repeat_button.setToolTip(
            {"off": "リピート: オフ", "all": "リピート: 全曲", "one": "リピート: 1曲"}[mode]
        )

    # --- user actions --------------------------------------------------------
    def _play_item(self, item: QListWidgetItem) -> None:
        self.owner.play_from_playlist(self.list.row(item))

    def _show_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        row = self.list.row(item)
        menu = QMenu(self.list)
        play_from = menu.addAction("この曲から再生")
        play_only = menu.addAction("この曲だけ再生")
        menu.addSeparator()
        remove = menu.addAction("削除")
        action = menu.exec(self.list.viewport().mapToGlobal(pos))
        if action == play_from:
            self.owner.play_from_playlist(row)
        elif action == play_only:
            self.owner.play_from_playlist(row, single=True)
        elif action == remove:
            if not item.isSelected():
                self.list.clearSelection()
                item.setSelected(True)
            self._remove_selected()

    def _reordered(self) -> None:
        self.owner.set_playlist(self._paths())

    def _remove_selected(self) -> None:
        rows = sorted((self.list.row(item) for item in self.list.selectedItems()), reverse=True)
        for row in rows:
            self.list.takeItem(row)
        if rows:
            self.owner.set_playlist(self._paths())

    def _add_files(self) -> None:
        last = Path(self.owner.config.get("last_midi", ""))
        initial = str(last.parent) if last.parent.is_dir() else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "プレイリストに追加", initial,
            "MIDIファイル (*.mid *.midi);;すべてのファイル (*.*)")
        if paths:
            self.owner.add_to_playlist(paths)

    def _toggle_shuffle(self) -> None:
        self.owner.set_shuffle(not self.owner.playlist_shuffle)
        self.refresh_modes()

    def _cycle_repeat(self) -> None:
        self.owner.set_repeat({"off": "all", "all": "one", "one": "off"}[self.owner.playlist_repeat])
        self.refresh_modes()


class ResonanceMidiWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.config = load_config()
        self.song: MidiSong | None = None
        self.windows: list[WindowInfo] = []
        self.options_window: OptionsWindow | None = None
        self.instrument_window: InstrumentWindow | None = None
        self.playlist_window: PlaylistWindow | None = None
        self._track_position = False
        self.position_save_timer = QTimer(self)
        self.position_save_timer.setSingleShot(True)
        self.position_save_timer.setInterval(300)
        self.position_save_timer.timeout.connect(self.save)
        self.seeking = False
        self.countdown_remaining = 0
        self.sustain_check_pending = False
        self.speed = float(self.config.get("speed", 1.0))
        self.transpose = int(self.config.get("transpose", 0))
        self.press_ms = int(self.config.get("press_ms", 80))
        self.octave_switch_ms = int(self.config.get("octave_switch_ms", 18))
        self.ignore_drums = bool(self.config.get("ignore_drums", True))
        self.instrument = str(self.config.get("instrument", DEFAULT_INSTRUMENT))
        if not instrument_profile(self.instrument).selectable:
            self.instrument = DEFAULT_INSTRUMENT
        self.unlock_stage = instrument_profile(self.instrument).clamp_stage(
            self.config.get("unlock_stage", DEFAULT_UNLOCK_STAGE)
        )
        self.range_correction = bool(self.config.get("range_correction", False))
        # Auto octave switching is always on now (nobody plays without it); the
        # checkbox was removed. The config key is kept but no longer consulted.
        self.auto_octave = True
        self.game_octave_offset = max(-3, min(3, int(self.config.get("game_octave_offset", 0))))
        self.countdown = max(0, min(10, int(self.config.get("countdown", 3))))
        self.sustain_check = bool(self.config.get("check_sustain_state", True))
        self.topmost = bool(self.config.get("topmost", False))
        self.opacity = max(0.5, min(1.0, float(self.config.get("opacity", 0.8))))
        self.ui_scale = max(0.5, min(2.0, round(float(self.config.get("ui_scale", 1.0)), 1)))
        self.playlist = [str(p) for p in self.config.get("playlist", []) if isinstance(p, str)]
        self.playlist_index = -1
        self.playlist_shuffle = bool(self.config.get("playlist_shuffle", False))
        self.playlist_repeat = str(self.config.get("playlist_repeat", "off"))
        if self.playlist_repeat not in ("off", "all", "one"):
            self.playlist_repeat = "off"
        self.playlist_gap = max(0, min(10, int(self.config.get("playlist_gap", 3))))
        self._play_single = False   # "この曲だけ再生": don't auto-advance at end
        self._shuffle_order: list[int] = []
        self._shuffle_pos = -1
        self._pending_countdown = self.countdown
        # Session-only: the playlist window remembers where it was put until the
        # app quits, but every launch reopens it at the default geometry.
        self._playlist_geometry: QRect | None = None
        self._duration_cache: dict[str, float | None] = {}
        # Stop playback if the game stops being the foreground window while
        # playing (keys would otherwise land on the tool or another app).
        self._playing_hwnd = 0
        self._suppress_focus_stop = False
        self._auto_stopped_at = 0.0
        self.setWindowTitle("Resonance MIDI Player")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(650, 190)
        self._build()
        self.scale_widget_tree(self)
        self.apply_background_style(self)

        self.bridge = PlayerBridge()
        self.bridge.position.connect(self._on_position)
        self.bridge.error.connect(self._on_error)
        self.player = MidiPlayer(send_key, self.bridge.position.emit, self.bridge.error.emit)
        self.sync_player_config()
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._countdown_tick)
        self.focus_watch = QTimer(self)
        self.focus_watch.setInterval(300)
        self.focus_watch.timeout.connect(self._check_focus)
        self.refresh_windows()
        self.set_topmost(self.topmost, save_value=False)
        self._restore_position()
        self._track_position = True
        last = self.config.get("last_midi", "")
        if last and Path(last).is_file():
            self.load_file(last, quiet=True)

    def panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        return panel

    def show_alert(self, title: str, message: str) -> None:
        AlertDialog(self, title, message).exec()

    def show_info(self, title: str, message: str) -> None:
        AlertDialog(self, title, message, kind="info").exec()

    def _duration_for(self, path: str) -> float | None:
        """Song length in seconds for the list, parsed once and cached."""
        if path not in self._duration_cache:
            try:
                self._duration_cache[path] = load_midi(path).duration
            except (MidiError, OSError):
                self._duration_cache[path] = None
        return self._duration_cache[path]

    def _apply_playlist_default_geometry(self, window: "PlaylistWindow") -> None:
        # Width matches the main window; height fits about six rows. Then anchor
        # it just below the main window like the other popouts start out.
        window.resize(self.width(), round(310 * self.ui_scale))
        self._anchor_popout(window)

    def icon_button(self, icon: QIcon, tooltip: str, size: int = 36) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(QPixmap(icon.pixmap(20, 20)).size())
        button.setToolTip(tooltip)
        button.setFixedSize(size, 30)
        button.setObjectName("iconButton")
        return button

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        accent = QFrame()
        accent.setObjectName("accentBar")
        accent.setFixedWidth(4)
        outer.addWidget(accent)
        shell = QFrame()
        shell.setObjectName("shell")
        outer.addWidget(shell, 1)
        body = QVBoxLayout(shell)
        body.setContentsMargins(8, 0, 8, 8)
        body.setSpacing(0)

        header = DragBar()
        header.setObjectName("header")
        header.setFixedHeight(30)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 0, 0)
        title = QLabel("RESONANCE MIDI")
        title.setObjectName("windowTitle")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.playlist_button = self.icon_button(simple_icon("list", WHITE, 18), "プレイリスト", 32)
        self.playlist_button.clicked.connect(self.open_playlist)
        self.instrument_button = self.icon_button(eighth_note_icon(18), "楽器・音域補正（ベータ）", 32)
        self.instrument_button.clicked.connect(self.open_instruments)
        self.gear_button = self.icon_button(gear_icon(18), "オプション", 32)
        self.gear_button.clicked.connect(self.open_options)
        self.close_button = self.icon_button(simple_icon("close", WHITE, 15), "閉じる", 32)
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.playlist_button)
        header_layout.addWidget(self.instrument_button)
        header_layout.addWidget(self.gear_button)
        header_layout.addWidget(self.close_button)
        body.addWidget(header)
        body.addSpacing(2)

        self.file_panel = self.panel()
        self.file_panel.setFixedHeight(57)
        file_stack = QStackedLayout(self.file_panel)
        file_stack.setContentsMargins(0, 0, 0, 0)
        file_stack.setSpacing(0)
        file_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.spectrum = MidiSpectrumWidget()
        file_stack.addWidget(self.spectrum)
        file_overlay = QWidget()
        file_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        file_layout = QHBoxLayout(file_overlay)
        file_layout.setContentsMargins(8, 6, 8, 6)
        file_layout.setSpacing(10)
        self.choose_button = QPushButton("＋ MIDI")
        self.choose_button.setObjectName("midiButton")
        self.choose_button.setFixedSize(81, 34)
        self.choose_button.clicked.connect(self.choose_file)
        file_layout.addWidget(self.choose_button)
        info = QVBoxLayout()
        info.setSpacing(0)
        self.song_title = ElidedLabel("MIDIファイルを選択してください")
        self.song_title.setObjectName("songTitle")
        self.song_meta = ElidedLabel("SMF format 0 / 1")
        self.song_meta.setObjectName("metaLabel")
        info.addWidget(self.song_title)
        info.addWidget(self.song_meta)
        file_layout.addLayout(info, 1)
        file_stack.addWidget(file_overlay)
        file_stack.setCurrentWidget(file_overlay)
        body.addWidget(self.file_panel)
        body.addSpacing(4)

        self.transport_panel = self.panel()
        self.transport_panel.setFixedHeight(45)
        transport_layout = QHBoxLayout(self.transport_panel)
        transport_layout.setContentsMargins(8, 6, 8, 6)
        transport_layout.setSpacing(6)
        self.current_time = QLabel("0:00")
        self.current_time.setObjectName("strongLabel")
        self.current_time.setFixedWidth(35)
        transport_layout.addWidget(self.current_time)
        self.seek = SeekSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1)
        self.seek.sliderPressed.connect(self._seek_pressed)
        self.seek.sliderReleased.connect(self._seek_released)
        self.seek.valueChanged.connect(self._seek_preview)
        self.seek.jumped.connect(self._seek_jumped)
        transport_layout.addWidget(self.seek, 1)
        self.total_time = QLabel("0:00")
        self.total_time.setFixedWidth(35)
        self.total_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        transport_layout.addWidget(self.total_time)
        restart = self.icon_button(simple_icon("restart", WHITE, 17), "先頭から", 36)
        restart.clicked.connect(lambda: self.player.restart(False))
        transport_layout.addWidget(restart)
        self.play_button = self.icon_button(simple_icon("play", WHITE, 17), "再生", 40)
        self.play_button.setObjectName("playButton")
        self.play_button.clicked.connect(self.play_button_clicked)
        transport_layout.addWidget(self.play_button)
        body.addWidget(self.transport_panel)
        self.countdown_label = QLabel("", self.transport_panel)
        self.countdown_label.setObjectName("countdownLabel")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.countdown_label.setFixedSize(72, 43)
        self.countdown_effect = QGraphicsOpacityEffect(self.countdown_label)
        self.countdown_label.setGraphicsEffect(self.countdown_effect)
        self.countdown_animation = QPropertyAnimation(self.countdown_effect, b"opacity", self)
        self.countdown_animation.setDuration(900)
        self.countdown_animation.setStartValue(1.0)
        self.countdown_animation.setEndValue(0.0)
        self.countdown_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.countdown_label.hide()
        body.addSpacing(4)

        self.target_panel = self.panel()
        self.target_panel.setFixedHeight(38)
        target_layout = QHBoxLayout(self.target_panel)
        target_layout.setContentsMargins(8, 4, 8, 4)
        target_layout.setSpacing(6)
        target_label = QLabel("対象")
        target_label.setObjectName("strongLabel")
        target_label.setFixedWidth(35)
        target_layout.addWidget(target_label)
        self.target_combo = QComboBox()
        self.target_combo.currentTextChanged.connect(self._target_changed)
        target_layout.addWidget(self.target_combo, 1)
        self.refresh_button = self.icon_button(simple_icon("refresh", WHITE, 16), "ウィンドウを更新", 40)
        self.refresh_button.clicked.connect(self.refresh_windows)
        target_layout.addWidget(self.refresh_button)
        body.addWidget(self.target_panel)

    def apply_background_style(self, widget: QWidget) -> None:
        alpha = round(self.opacity * 255)
        px = lambda value: max(1, round(value * self.ui_scale))
        widget.setStyleSheet(f"""
            QWidget {{ color: {WHITE}; font-family: "Yu Gothic UI"; font-size: {px(12)}px; }}
            QFrame#shell {{ background-color: rgba(0, 0, 0, {alpha}); border: {px(1)}px solid rgba(189, 247, 255, 75); }}
            QFrame#accentBar {{ background-color: {ACCENT}; border: none; }}
            QFrame#header {{ background: transparent; border: none; }}
            QFrame#panel {{ background: transparent; border: {px(1)}px solid rgba(189, 247, 255, 65); }}
            QLabel {{ color: {WHITE}; background: transparent; border: none; }}
            QLabel:disabled {{ color: rgba(255, 255, 255, 90); }}
            QComboBox:disabled {{ background-color: #14171b; color: rgba(255, 255, 255, 90); border-color: #23272d; }}
            QLabel#windowTitle {{ font-weight: 700; color: {WHITE}; }}
            QLabel#songTitle {{ font-size: {px(13)}px; font-weight: 700; color: {WHITE}; }}
            QLabel#metaLabel {{ color: {WHITE}; }}
            QLabel#strongLabel {{ font-weight: 700; color: {WHITE}; }}
            QLabel#sectionTitle {{ font-size: {px(15)}px; font-weight: 700; color: {WHITE}; }}
            QLabel#countdownLabel {{ font-size: {px(24)}px; font-weight: 800; color: {WHITE}; background: transparent; }}
            QToolButton#iconButton {{ background: transparent; border: none; }}
            QToolButton#iconButton:hover {{ background-color: rgba(70, 90, 110, 190); }}
            QToolButton#stepButton {{ background-color: #242a31; border: {px(1)}px solid #343b44; }}
            QToolButton#stepButton:hover {{ background-color: #39434e; }}
            QToolButton#playButton {{ background-color: {PLAY_BLUE}; border: none; }}
            QToolButton#playButton:hover {{ background-color: #3194e7; }}
            QToolButton#playButton[running="true"] {{ background-color: {STOP_RED}; }}
            QToolButton#playButton[running="true"]:hover {{ background-color: #e0525a; }}
            QPushButton#midiButton {{ background-color: #bdf7ff; color: #101010; border: none; font-weight: 700; }}
            QPushButton#midiButton:hover {{ background-color: #d9fbff; }}
            QComboBox, QSpinBox {{ background-color: #171b20; color: {WHITE}; border: {px(1)}px solid #343b44; padding: {px(4)}px {px(7)}px; selection-background-color: #29465f; selection-color: {WHITE}; }}
            QComboBox QAbstractItemView {{ background-color: #171b20; color: {WHITE}; border: {px(1)}px solid #343b44; selection-background-color: #29465f; selection-color: {WHITE}; }}
            QComboBox::drop-down {{ border: none; width: {px(22)}px; }}
            QSpinBox::up-button, QSpinBox::down-button {{ background-color: #242a31; border: none; width: {px(18)}px; }}
            QCheckBox {{ color: {WHITE}; spacing: {px(6)}px; }}
            QSlider::groove:horizontal {{ height: {px(6)}px; background-color: #171b20; border-radius: {px(3)}px; }}
            QSlider::sub-page:horizontal {{ background-color: #171b20; border-radius: {px(3)}px; }}
            QSlider::handle:horizontal {{ width: {px(12)}px; margin: -{px(4)}px 0; background-color: {WHITE}; border-radius: {px(6)}px; }}
            QPushButton#chipButton {{ background-color: #242a31; color: {WHITE}; border: {px(1)}px solid #343b44; padding: {px(5)}px {px(12)}px; }}
            QPushButton#chipButton:hover {{ background-color: #39434e; }}
            QListWidget#playlist {{ background-color: #14171b; border: {px(1)}px solid #343b44; outline: none; }}
            QListWidget#playlist::item {{ padding: {px(5)}px {px(6)}px; border: none; }}
            QListWidget#playlist::item:selected {{ background-color: #29465f; color: {WHITE}; }}
            QListWidget#playlist::item:hover {{ background-color: rgba(70, 90, 110, 90); }}
            QMenu {{ background-color: #171b20; color: {WHITE}; border: {px(1)}px solid #343b44; }}
            QMenu::item {{ padding: {px(5)}px {px(22)}px; }}
            QMenu::item:selected {{ background-color: #29465f; }}
            QMenu::separator {{ height: {px(1)}px; background-color: #343b44; margin: {px(4)}px {px(6)}px; }}
        """)

    def scale_widget_tree(self, root: QWidget) -> None:
        """Scale fixed geometry, layout spacing and icons from stored 1.0x metrics."""
        scale = self.ui_scale
        widgets = [root, *root.findChildren(QWidget)]
        for child in widgets:
            if not hasattr(child, "_ui_base_minimum"):
                child._ui_base_minimum = QSize(child.minimumSize())
                child._ui_base_maximum = QSize(child.maximumSize())
                if isinstance(child, QToolButton):
                    child._ui_base_icon_size = QSize(child.iconSize())
            base_min = child._ui_base_minimum
            base_max = child._ui_base_maximum
            minimum = QSize(round(base_min.width() * scale), round(base_min.height() * scale))
            maximum = QSize(
                base_max.width() if base_max.width() >= 16777215 else round(base_max.width() * scale),
                base_max.height() if base_max.height() >= 16777215 else round(base_max.height() * scale),
            )
            child.setMinimumSize(QSize(0, 0))
            child.setMaximumSize(maximum)
            child.setMinimumSize(minimum)
            if isinstance(child, QToolButton):
                icon_size = child._ui_base_icon_size
                child.setIconSize(QSize(
                    max(1, round(icon_size.width() * scale)),
                    max(1, round(icon_size.height() * scale)),
                ))

        layouts: list[QLayout] = []
        if root.layout() is not None:
            layouts.append(root.layout())
        layouts.extend(root.findChildren(QLayout))
        seen: set[int] = set()
        for layout in layouts:
            if id(layout) in seen:
                continue
            seen.add(id(layout))
            if not hasattr(layout, "_ui_base_margins"):
                margins = layout.contentsMargins()
                layout._ui_base_margins = (
                    margins.left(), margins.top(), margins.right(), margins.bottom()
                )
                layout._ui_base_spacing = layout.spacing()
            left, top, right, bottom = layout._ui_base_margins
            layout.setContentsMargins(
                round(left * scale), round(top * scale),
                round(right * scale), round(bottom * scale),
            )
            if layout._ui_base_spacing >= 0:
                layout.setSpacing(round(layout._ui_base_spacing * scale))
        self.apply_background_style(root)
        base_min = root._ui_base_minimum
        base_max = root._ui_base_maximum
        if base_min == base_max:
            if root.layout() is not None:
                root.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            root.setFixedSize(
                max(1, round(base_min.width() * scale)),
                max(1, round(base_min.height() * scale)),
            )
        root.updateGeometry()

    def set_ui_scale(self, value: float) -> None:
        value = max(0.5, min(2.0, round(float(value), 1)))
        old_scale = self.ui_scale
        playlist_rect = None
        if self.playlist_window is not None:
            playlist_rect = QRect(self.playlist_window.geometry())
        elif self._playlist_geometry is not None:
            playlist_rect = QRect(self._playlist_geometry)
        self.ui_scale = value
        self.config["ui_scale"] = value
        self.scale_widget_tree(self)
        if self.instrument_window is not None:
            self.scale_widget_tree(self.instrument_window)
        if self.playlist_window is not None:
            self.scale_widget_tree(self.playlist_window)
            if playlist_rect is not None:
                scaled = self._scale_playlist_rect(playlist_rect, old_scale, value)
                self.playlist_window.setGeometry(scaled)
                self._keep_window_on_screen(self.playlist_window)
                self._playlist_geometry = QRect(self.playlist_window.geometry())
        elif playlist_rect is not None:
            # The popout remembers its geometry for this session even while
            # closed. Keep that remembered size in the same logical UI units.
            self._playlist_geometry = self._scale_playlist_rect(playlist_rect, old_scale, value)
        if self.options_window is not None:
            self.scale_widget_tree(self.options_window)
            self.options_window.scale_value.setText(f"{value:.1f}x")
            self.options_window.scale_slider.blockSignals(True)
            self.options_window.scale_slider.setValue(round(value * 10))
            self.options_window.scale_slider.blockSignals(False)
        self._keep_on_screen()
        self.anchor_options()
        self.save()

    @staticmethod
    def _scale_playlist_rect(rect: QRect, old_scale: float, new_scale: float) -> QRect:
        ratio = new_scale / old_scale if old_scale > 0 else 1.0
        return QRect(
            rect.x(),
            rect.y(),
            max(1, round(rect.width() * ratio)),
            max(1, round(rect.height() * ratio)),
        )

    @staticmethod
    def _keep_window_on_screen(window: QWidget) -> None:
        screen = QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(window.x(), area.left()), max(area.left(), area.right() - window.width() + 1))
        y = min(max(window.y(), area.top()), max(area.top(), area.bottom() - window.height() + 1))
        if (x, y) != (window.x(), window.y()):
            window.move(x, y)

    def _keep_on_screen(self) -> None:
        self._keep_window_on_screen(self)

    def choose_file(self) -> None:
        last = Path(self.config.get("last_midi", ""))
        initial = str(last.parent) if last.parent.is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(self, "MIDIファイルを選択", initial, "MIDIファイル (*.mid *.midi);;すべてのファイル (*.*)")
        if path:
            # A single file chosen with ＋MIDI leaves playlist mode: no badge,
            # no auto-advance, and the current-song marker is cleared.
            self.playlist_index = -1
            self._mark_playlist()
            self.load_file(path)

    def load_file(self, path: str, quiet: bool = False) -> None:
        try:
            song = load_midi(path)
        except (MidiError, OSError) as exc:
            if not quiet:
                self.show_alert("MIDI読込エラー", str(exc))
            return
        self.song = song
        self.player.load(song)
        self.sync_player_config()
        self.config["last_midi"] = str(song.path)
        self.save()
        # Show the file name, not the embedded track name: users control the
        # former (matches the playlist rows).
        self.song_title.setText(Path(song.path).stem)
        range_text = "音符なし"
        if song.note_range:
            low, high = song.note_range
            range_text = f"{note_name(low)}–{note_name(high)}"
        self.song_meta.setText(
            f"{len(song.notes):,} notes  •  {len(song.track_names)} tracks  •  {range_text}  •  {song.initial_bpm:.0f} BPM"
        )
        self.total_time.setText(format_time(song.duration))
        self.seek.setRange(0, max(1, round(song.duration * 1000)))

    def play_button_clicked(self) -> None:
        if self._is_running():
            self.stop()
            return
        # Clicking the tool steals focus, so the focus-watch may have just
        # auto-stopped playback for this very click. Don't bounce back into play.
        if time.monotonic() - self._auto_stopped_at < 0.6:
            return
        if not self.song:
            if self.playlist:
                self.play_from_playlist(self._first_playlist_index())
            else:
                self.choose_file()
            return
        self._request_playback()

    def _is_running(self) -> bool:
        return (self.player.state == "playing" or self.countdown_timer.isActive()
                or self.sustain_check_pending)

    def _request_playback(self, countdown: int | None = None) -> None:
        """Focus the game, optionally check sustain, then start with a countdown."""
        self._pending_countdown = self.countdown if countdown is None else countdown
        self.sync_player_config()
        target = self._focus_target()
        self._playing_hwnd = target.hwnd if target else 0
        # Drums have no sustain pedal, so the check is skipped for them even if
        # the (now disabled) checkbox is left ticked.
        if self.sustain_check and self.instrument != "drums":
            if target is None:
                self._show_sustain_absent()
                return
            self.sustain_check_pending = True
            self._set_running(True)
            QTimer.singleShot(250, lambda hwnd=target.hwnd: self._finish_sustain_check(hwnd))
            return
        self._begin_playback()

    def _begin_playback(self) -> None:
        # The game is already focused here. Prepare the seek destination's
        # keyboard view before the countdown reaches zero.
        self.player.prepare_for_playback()
        if self._pending_countdown <= 0:
            self.player.play()
        else:
            self.countdown_remaining = self._pending_countdown
            self._show_countdown(self.countdown_remaining)
            self.countdown_timer.start()
        self._set_running(True)
        self.focus_watch.start()

    def _check_focus(self) -> None:
        """Stop if the game lost the foreground while we are playing (option A)."""
        if not self._is_running():
            self.focus_watch.stop()
            return
        if self._suppress_focus_stop or not self._playing_hwnd:
            return
        if foreground_window() != self._playing_hwnd:
            self._auto_stopped_at = time.monotonic()
            self.stop()

    def stop(self) -> None:
        self.sustain_check_pending = False
        self.countdown_timer.stop()
        self.focus_watch.stop()
        self._hide_countdown()
        if self.player.keyboard_shifted:
            self._focus_target()
        self.player.stop()
        self._set_running(False)

    def _capture_window(self, hwnd: int):
        """Capture the focused game in physical pixels, independent of DPI."""
        rect = window_rect(hwnd)
        if rect is None:
            return []
        image = capture_screen_rect(rect)
        return [] if image.isNull() else [image]

    def _finish_sustain_check(self, hwnd: int) -> None:
        if not self.sustain_check_pending:
            return
        self.sustain_check_pending = False
        images = self._capture_window(hwnd)
        if not images:
            self._disable_sustain_check()
            self.show_alert(
                "サステイン状態の確認",
                "サステイン状態が取得できませんでした。\n"
                "以降サステイン状態のチェックは行いません。",
            )
            self._set_running(False)
            return
        detections = [detect_sustain_state(image) for image in images]
        detection = next(
            (item for item in detections if item.state in (SustainState.ON, SustainState.OFF)),
            next(
                (item for item in detections if item.state is SustainState.ABSENT),
                detections[0],
            ),
        )
        if detection.state is SustainState.ON:
            self._begin_playback()
            return
        self._set_running(False)
        if detection.state is SustainState.OFF:
            self.show_alert(
                "サステインをオンにしてください",
                "サステイン [Space] をオンにしてください。\n\n"
                "オンにしてもこのメッセージが出る場合は、オプションで"
                "「サステイン状態のチェック」をオフにしてください。",
            )
        elif detection.state is SustainState.ABSENT:
            self._show_sustain_absent()
        else:
            self._disable_sustain_check()
            self.show_alert(
                "サステイン状態の確認",
                "サステイン状態が取得できませんでした。\n"
                "以降サステイン状態のチェックは行いません。",
            )

    def _show_sustain_absent(self) -> None:
        self._set_running(False)
        self.show_alert(
            "演奏モードを確認してください",
            "「サステインペダル [Space]」が画面上に見つかりませんでした。\n"
            "ゲーム側が演奏モードでない可能性があるので、演奏モードにしてください。\n\n"
            "演奏モードにしても、このメッセージが出る場合は、オプションで"
            "「サステイン状態のチェック」をオフにしてください。",
        )

    def _disable_sustain_check(self) -> None:
        self.sustain_check = False
        self.config["check_sustain_state"] = False
        self.save()
        if self.instrument_window is not None:
            checkbox = self.instrument_window.sustain_check
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)

    def _countdown_tick(self) -> None:
        self.countdown_remaining -= 1
        if self.countdown_remaining <= 0:
            self.countdown_timer.stop()
            self._hide_countdown()
            self.player.play()
        else:
            self._show_countdown(self.countdown_remaining)

    def _show_countdown(self, value: int) -> None:
        if value <= 0:
            self._hide_countdown()
            return
        self._position_countdown()
        self.countdown_animation.stop()
        self.countdown_effect.setOpacity(1.0)
        self.countdown_label.setText(str(value))
        self.countdown_label.show()
        self.countdown_label.raise_()
        self.countdown_animation.start()

    def _hide_countdown(self) -> None:
        self.countdown_animation.stop()
        self.countdown_label.hide()

    def _position_countdown(self) -> None:
        origin = self.seek.mapTo(self.transport_panel, QPoint(0, 0))
        x = origin.x() + (self.seek.width() - self.countdown_label.width()) // 2
        y = (self.transport_panel.height() - self.countdown_label.height()) // 2
        self.countdown_label.move(x, y)

    def _set_running(self, running: bool) -> None:
        self.play_button.setProperty("running", running)
        self.play_button.setIcon(simple_icon("stop" if running else "play", WHITE, 17))
        self.play_button.setToolTip("停止" if running else "再生")
        self.play_button.style().unpolish(self.play_button)
        self.play_button.style().polish(self.play_button)

    def _seek_pressed(self) -> None:
        self.seeking = True

    def _seek_preview(self, value: int) -> None:
        if self.seeking:
            self.current_time.setText(format_time(value / 1000.0))

    def _seek_released(self) -> None:
        self.seeking = False
        if self.player.keyboard_shifted:
            self._focus_target()
        self.player.seek(self.seek.value() / 1000.0)

    def _seek_jumped(self, value: int) -> None:
        self.current_time.setText(format_time(value / 1000.0))
        if self.player.keyboard_shifted:
            self._focus_target()
        self.player.seek(value / 1000.0)

    def _on_position(self, position: float, state: str) -> None:
        self.spectrum.set_position(position, state == "playing")
        if not self.seeking:
            self.seek.setValue(round(position * 1000))
            self.current_time.setText(format_time(position))
        if state != "playing":
            self._set_running(False)
            self.focus_watch.stop()
        # Only a natural end advances the playlist; a manual stop reports
        # "stopped" and leaves the queue where it is.
        if state == "ended" and self.playlist_index >= 0 and self.playlist:
            if self._play_single:
                # "この曲だけ再生": stop here, leave the queue untouched.
                self._play_single = False
                self.playlist_index = -1
                self._mark_playlist()
            else:
                self._advance_playlist()

    def _on_error(self, message: str) -> None:
        self._set_running(False)
        self.show_alert("再生エラー", message)

    def refresh_windows(self) -> None:
        self.windows = [item for item in list_windows() if item.title != self.windowTitle()]
        titles = [item.title for item in self.windows]
        saved = self.config.get("target_title", GAME_WINDOW_TITLE)
        match = next((title for title in titles if title == GAME_WINDOW_TITLE), None)
        if not match:
            match = next((title for title in titles if saved.casefold() in title.casefold()), None)
        current = match or saved
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItems(titles)
        if current not in titles:
            self.target_combo.addItem(current)
        self.target_combo.setCurrentText(current)
        self.target_combo.blockSignals(False)

    def _target_changed(self, title: str) -> None:
        if title:
            self.config["target_title"] = title
            self.save()

    def _focus_target(self) -> WindowInfo | None:
        wanted = self.target_combo.currentText() or GAME_WINDOW_TITLE
        window = next((item for item in self.windows if item.title == wanted), None)
        if window and focus_window(window.hwnd):
            return window
        self.refresh_windows()
        wanted = self.target_combo.currentText() or wanted
        window = next((item for item in self.windows if item.title == wanted), None)
        if window and focus_window(window.hwnd):
            return window
        return None

    def update_setting(self, key: str, value) -> None:
        setattr(self, {
            "auto_octave_switch": "auto_octave",
            "check_sustain_state": "sustain_check",
        }.get(key, key), value)
        self.config[key] = value
        self.save()
        self.sync_player_config()

    def sync_player_config(self) -> None:
        try:
            auto = self.auto_octave and self.game_octave_offset == 0
            if self.player.keyboard_shifted and not auto:
                self._focus_target()
            mapping = mapping_for_game_octave(default_mapping(), 0 if auto else self.game_octave_offset)
            self.player.configure(mapping, self.transpose, self.speed, self.press_ms,
                                  self.ignore_drums, auto, self.octave_switch_ms,
                                  self.instrument, self.unlock_stage, self.range_correction)
            self.spectrum.set_notes(self.player.audible_notes)
        except AttributeError:
            pass

    def export_audible_midi(self) -> None:
        """Write out exactly what the player will send, for listening to."""
        if self.song is None:
            self.show_alert("MIDIの書き出し", "先にMIDIファイルを読み込んでください。")
            return
        notes = self.player.audible_notes
        if not notes:
            self.show_alert("MIDIの書き出し",
                            "鳴らせる音がありません。楽器設定の音域を確認してください。")
            return
        source = Path(self.song.path)
        target, _ = QFileDialog.getSaveFileName(
            self, "補正結果の書き出し",
            str(source.with_name(f"{source.stem}.corrected.mid")),
            "MIDIファイル (*.mid)",
        )
        if not target:
            return
        try:
            written = write_midi(target, notes)
        except OSError as exc:
            self.show_alert("MIDIの書き出し", f"書き出しに失敗しました。\n{exc}")
            return
        stats = self.player.range_stats
        dropped = len(self.song.notes) - written
        self.show_alert(
            "MIDIの書き出し",
            f"{Path(target).name} を書き出しました。\n\n"
            f"書き出した音: {written}\n"
            f"音域補正で置き換えた音: {stats['folded_notes']}\n"
            f"鳴らないため除外した音: {dropped}",
        )

    def _close_other_popouts(self, keep: str) -> None:
        # Only one popout is ever visible; they all anchor to the same spot.
        for name in ("options_window", "instrument_window", "playlist_window"):
            if name != keep and getattr(self, name) is not None:
                getattr(self, name).close()

    # --- playlist ------------------------------------------------------------
    def add_to_playlist(self, paths: list[str]) -> None:
        existing = set(self.playlist)
        added = False
        for raw in paths:
            norm = str(Path(raw))
            if norm not in existing:
                self.playlist.append(norm)
                existing.add(norm)
                added = True
        if added:
            self._commit_playlist()
            if self.playlist_window is not None:
                self.playlist_window.refresh_rows()

    def set_playlist(self, paths: list[str]) -> None:
        """Replace the queue from a reorder/remove/clear in the window."""
        self.playlist = [str(Path(p)) for p in paths]
        self._commit_playlist()
        if self.playlist_window is not None:
            self.playlist_window.mark_current(self.playlist_index)

    def _commit_playlist(self) -> None:
        self._shuffle_order = []
        self._shuffle_pos = -1
        self.config["playlist"] = list(self.playlist)
        self._sync_playlist_index()
        self.save()

    def _sync_playlist_index(self) -> None:
        current = str(self.song.path) if self.song else None
        self.playlist_index = self.playlist.index(current) if current in self.playlist else -1

    def set_shuffle(self, value: bool) -> None:
        self.playlist_shuffle = bool(value)
        self._shuffle_order = []
        self._shuffle_pos = -1
        self.config["playlist_shuffle"] = self.playlist_shuffle
        self.save()

    def set_repeat(self, mode: str) -> None:
        self.playlist_repeat = mode
        self.config["playlist_repeat"] = mode
        self.save()

    def _mark_playlist(self) -> None:
        if self.playlist_window is not None:
            self.playlist_window.mark_current(self.playlist_index)

    def play_from_playlist(self, index: int, single: bool = False) -> None:
        if not (0 <= index < len(self.playlist)):
            return
        path = self.playlist[index]
        if not Path(path).is_file():
            self.show_alert("再生できません", f"ファイルが見つかりません:\n{path}")
            return
        if self._is_running():
            self.stop()
        # single=True ("この曲だけ再生"): play this one and stop, no auto-advance.
        self._play_single = single
        self.playlist_index = index
        self.load_file(path)
        self._mark_playlist()
        self._request_playback()

    def playlist_step(self, delta: int) -> None:
        """Manual previous/next: linear wrap, independent of shuffle/repeat."""
        count = len(self.playlist)
        if count == 0:
            return
        base = self.playlist_index if self.playlist_index >= 0 else 0
        self.play_from_playlist((base + delta) % count)

    def _advance_playlist(self) -> None:
        """Auto-play the next queued song after one ends naturally."""
        for _ in range(max(1, len(self.playlist))):
            index = self._next_playlist_index()
            if index is None:
                break
            self.playlist_index = index
            path = self.playlist[index]
            if Path(path).is_file():
                self.load_file(path, quiet=True)
                self._mark_playlist()
                self.sync_player_config()
                target = self._focus_target()
                self._playing_hwnd = target.hwnd if target else 0
                self._pending_countdown = self.playlist_gap
                self._begin_playback()
                return
            # Missing file: skip it and keep advancing.
        self.playlist_index = -1
        self._mark_playlist()

    def _next_playlist_index(self) -> int | None:
        count = len(self.playlist)
        if count == 0:
            return None
        if self.playlist_repeat == "one" and 0 <= self.playlist_index < count:
            return self.playlist_index
        if self.playlist_shuffle:
            return self._next_shuffle_index()
        nxt = self.playlist_index + 1
        if nxt < count:
            return nxt
        return 0 if self.playlist_repeat == "all" else None

    def _next_shuffle_index(self) -> int | None:
        count = len(self.playlist)
        if count == 1:
            return 0 if self.playlist_repeat == "all" else None
        if not self._shuffle_order or self._shuffle_pos + 1 >= len(self._shuffle_order):
            if self._shuffle_order and self.playlist_repeat != "all":
                return None  # one shuffled pass finished and repeat is off
            order = list(range(count))
            random.shuffle(order)
            if order[0] == self.playlist_index:  # don't replay the same song back-to-back
                order.append(order.pop(0))
            self._shuffle_order = order
            self._shuffle_pos = -1
        self._shuffle_pos += 1
        return self._shuffle_order[self._shuffle_pos]

    def _first_playlist_index(self) -> int:
        if not self.playlist:
            return -1
        if self.playlist_shuffle:
            self._shuffle_order = []
            self._shuffle_pos = -1
            self.playlist_index = -1
            index = self._next_shuffle_index()
            return index if index is not None else 0
        return 0

    def open_options(self) -> None:
        # Header buttons toggle: a second press closes the panel they opened.
        if self.options_window is not None:
            self.options_window.close()
            return
        self._close_other_popouts("options_window")
        self.options_window = OptionsWindow(self)
        self.options_window.closed.connect(self._options_closed)
        self.anchor_options()
        self.options_window.show_front()

    def open_instruments(self) -> None:
        if self.instrument_window is not None:
            self.instrument_window.close()
            return
        self._close_other_popouts("instrument_window")
        self.instrument_window = InstrumentWindow(self)
        self.instrument_window.closed.connect(self._instrument_closed)
        self.anchor_options()
        self.instrument_window.show_front()

    def open_playlist(self) -> None:
        if self.playlist_window is not None:
            self.playlist_window.close()
            return
        self._close_other_popouts("playlist_window")
        self.playlist_window = PlaylistWindow(self)
        self.playlist_window.closed.connect(self._playlist_closed)
        # Session-remembered geometry if it was moved/resized this run, else the
        # default (main-width, six rows, anchored below the main window).
        if self._playlist_geometry is not None:
            self.playlist_window.setGeometry(self._playlist_geometry)
        else:
            self._apply_playlist_default_geometry(self.playlist_window)
        self.playlist_window.show_front()

    def anchor_options(self) -> None:
        # The playlist window floats freely (it is user-movable and remembers
        # its own spot), so it is deliberately not re-anchored here.
        for window in (self.options_window, self.instrument_window):
            if window is not None:
                self._anchor_popout(window)

    def _anchor_popout(self, window: QWidget) -> None:
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen is None:
            window.move(self.x(), self.y() + self.height() + 1)
            return
        area = screen.availableGeometry()
        gap = max(1, round(self.ui_scale))
        x = min(
            max(self.x(), area.left()),
            max(area.left(), area.right() - window.width() + 1),
        )
        below = self.y() + self.height() + gap
        above = self.y() - window.height() - gap
        if below + window.height() - 1 <= area.bottom():
            y = below
        elif above >= area.top():
            y = above
        else:
            y = area.top()
        window.move(x, y)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.anchor_options()
        if self._track_position:
            self.config["window_x"] = self.x()
            self.config["window_y"] = self.y()
            self.position_save_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._position_countdown)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_countdown)

    def _restore_position(self) -> None:
        try:
            x = int(self.config.get("window_x"))
            y = int(self.config.get("window_y"))
        except (TypeError, ValueError):
            return
        saved_rect = QRect(x, y, self.width(), self.height())
        if any(screen.availableGeometry().intersects(saved_rect) for screen in QApplication.screens()):
            self.move(x, y)

    def _popout_closing(self) -> None:
        """Closing a panel is exempt from the focus-stop: hand focus back to the
        game and keep playing (so the playlist window can be dismissed mid-song).
        """
        if not self._is_running():
            return
        self._suppress_focus_stop = True
        target = self._focus_target()
        if target:
            self._playing_hwnd = target.hwnd
        QTimer.singleShot(700, lambda: setattr(self, "_suppress_focus_stop", False))

    def _options_closed(self) -> None:
        self._popout_closing()
        if self.options_window is not None:
            self.options_window.deleteLater()
        self.options_window = None

    def _instrument_closed(self) -> None:
        self._popout_closing()
        if self.instrument_window is not None:
            self.instrument_window.deleteLater()
        self.instrument_window = None

    def _playlist_closed(self) -> None:
        self._popout_closing()
        if self.playlist_window is not None:
            self.playlist_window.deleteLater()
        self.playlist_window = None

    def set_topmost(self, value: bool, save_value: bool = True) -> None:
        self.topmost = bool(value)
        flags = self.windowFlags()
        if self.topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()
        if save_value:
            self.config["topmost"] = self.topmost
            self.save()
        if self.options_window is not None:
            self.options_window.show_front()

    def save(self) -> None:
        try:
            save_config(self.config)
        except OSError:
            pass

    def closeEvent(self, event) -> None:
        self.sustain_check_pending = False
        self.countdown_timer.stop()
        self.position_save_timer.stop()
        self.config["window_x"] = self.x()
        self.config["window_y"] = self.y()
        if self.options_window is not None:
            self.options_window.close()
        if self.instrument_window is not None:
            self.instrument_window.close()
        if self.playlist_window is not None:
            self.playlist_window.close()
        if self.player.keyboard_shifted:
            self._focus_target()
        self.player.close()
        self.save()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Resonance MIDI Player")
    app.setStyle("Fusion")
    # Let Explorer drop MIDIs onto the (elevated) app. Process-wide, set before
    # any window registers its drop target.
    allow_drag_drop()
    window = ResonanceMidiWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
