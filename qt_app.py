from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
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
from keyboard_input import WindowInfo, focus_window, list_windows, send_key, window_rect
from midi_parser import MidiError, MidiSong, load_midi, note_name
from midi_writer import write_midi
from player import MidiPlayer
from sustain_detector import SustainState, capture_screen_rect, detect_sustain_state


GAME_WINDOW_TITLE = "ブループロトコル：スターレゾナンス"
OCTAVE_LABELS = tuple(
    f"{offset:+d} オクターブ（Z = C{3 + offset}）" if offset else "初期位置（Z = C3）"
    for offset in range(-3, 4)
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


def keyboard_icon(size: int = 18) -> QIcon:
    """A keyboard seen head on: the case with three black keys hanging in it.

    Drawing the black keys as strokes rather than filled rectangles keeps them
    apart at the 18px the header actually uses; filled keys merge into a block.
    """
    return svg_icon(f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
         stroke="{ICON_BLUE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2.5" y="6" width="19" height="12" rx="1.5"/>
      <path stroke-width="2.2" stroke-linecap="butt" d="M7.6 6.5v5.2M12 6.5v5.2M16.4 6.5v5.2"/>
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

    def __init__(self, parent: QWidget, title: str, message: str):
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("alertShell")
        outer.addWidget(shell)

        body = QVBoxLayout(shell)
        body.setContentsMargins(px(16), 0, px(16), px(14))
        body.setSpacing(px(12))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        warning = QLabel("!")
        warning.setObjectName("alertMark")
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setFixedSize(px(30), px(30))
        header.addWidget(warning)
        title_label = QLabel(title)
        title_label.setObjectName("alertTitle")
        header.addWidget(title_label)
        header.addStretch()
        close = QToolButton()
        close.setObjectName("alertClose")
        close.setIcon(simple_icon("close", WHITE, px(14)))
        close.setIconSize(QSize(px(14), px(14)))
        close.setFixedSize(px(34), px(34))
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
        message_label.setMinimumHeight(px(72))
        body.addWidget(message_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok = QPushButton("OK")
        ok.setObjectName("alertButton")
        ok.setFixedSize(px(104), px(32))
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        body.addLayout(buttons)

        self.setStyleSheet(f"""
            QDialog {{ background: transparent; }}
            QFrame#alertShell {{
                background-color: rgba(8, 12, 17, 248);
                border: {px(2)}px solid #e0525a;
            }}
            QLabel {{
                color: {WHITE};
                background: transparent;
                border: none;
                font-family: "Yu Gothic UI";
                font-size: {px(13)}px;
            }}
            QLabel#alertMark {{
                color: {WHITE};
                background-color: #b8323b;
                border: {px(1)}px solid #ff747c;
                border-radius: {px(15)}px;
                font-size: {px(20)}px;
                font-weight: 800;
            }}
            QLabel#alertTitle {{
                color: {WHITE};
                font-size: {px(15)}px;
                font-weight: 700;
            }}
            QLabel#alertMessage {{ color: {WHITE}; }}
            QFrame#alertDivider {{ background-color: rgba(224, 82, 90, 150); border: none; }}
            QToolButton#alertClose {{ background: transparent; border: none; }}
            QToolButton#alertClose:hover {{ background-color: rgba(224, 82, 90, 80); }}
            QPushButton#alertButton {{
                color: {WHITE};
                background-color: #a62f37;
                border: {px(1)}px solid #f06a72;
                font-family: "Yu Gothic UI";
                font-size: {px(13)}px;
                font-weight: 700;
            }}
            QPushButton#alertButton:hover {{ background-color: #c83d45; }}
            QPushButton#alertButton:pressed {{ background-color: #84262d; }}
        """)
        self.adjustSize()
        self.setFixedHeight(max(px(180), self.sizeHint().height()))

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

    def __init__(self, owner: "ResonanceMidiWindow", width: int, height: int):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(f"Resonance MIDI Player - {self.heading.title()}")
        self.setFixedSize(width, height)
        self._build(self._build_chrome())
        self.owner.scale_widget_tree(self)
        self.owner.apply_background_style(self)

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
        close = self.owner.icon_button(simple_icon("close", WHITE, 15), "閉じる", 32)
        close.clicked.connect(self.close)
        header_layout.addWidget(close)
        body.addWidget(header)
        return body

    def _build(self, body: QVBoxLayout) -> None:
        raise NotImplementedError

    def _form_row(self, layout: QVBoxLayout, label: str, control: QWidget) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(label))
        row.addStretch()
        control.setMinimumWidth(215)
        row.addWidget(control)
        layout.addLayout(row)

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
        super().__init__(owner, 650, 326)

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

        press = ArrowSpinBox()
        press.setRange(0, 2000)
        press.setValue(self.owner.press_ms)
        press.valueChanged.connect(lambda value: self.owner.update_setting("press_ms", value))
        self._form_row(layout, "キー保持 ms", press)

        octave = QComboBox()
        octave.addItems(OCTAVE_LABELS)
        octave.setCurrentIndex(self.owner.game_octave_offset + 3)
        octave.currentIndexChanged.connect(lambda index: self.owner.update_setting("game_octave_offset", index - 3))
        self._form_row(layout, "ゲーム側の音域", octave)

        switch = ArrowSpinBox()
        switch.setRange(0, 100)
        switch.setValue(self.owner.octave_switch_ms)
        switch.valueChanged.connect(lambda value: self.owner.update_setting("octave_switch_ms", value))
        self._form_row(layout, "音域切替待機 ms", switch)

        drums = QCheckBox("ドラム（MIDI ch.10）を除外")
        drums.setChecked(self.owner.ignore_drums)
        drums.toggled.connect(lambda value: self.owner.update_setting("ignore_drums", value))
        layout.addWidget(drums)
        auto = QCheckBox("4オクターブ自動切替（譜面先読み・開始時 Z=C3）")
        auto.setChecked(self.owner.auto_octave)
        auto.toggled.connect(lambda value: self.owner.update_setting("auto_octave_switch", value))
        layout.addWidget(auto)
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
        self.sustain_check = QCheckBox("サステイン状態のチェック")
        self.sustain_check.setChecked(self.owner.sustain_check)
        self.sustain_check.toggled.connect(
            lambda value: self.owner.update_setting("check_sustain_state", value)
        )
        layout.addWidget(self.sustain_check)
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
    heading = "INSTRUMENT"

    def __init__(self, owner: "ResonanceMidiWindow"):
        super().__init__(owner, 650, 244)

    def _build(self, body: QVBoxLayout) -> None:
        panel = self.owner.panel()
        body.addWidget(panel, 1)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        heading = QLabel("楽器設定")
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
        self._form_row(layout, "楽器", self.instrument)

        self.stage = QComboBox()
        self.stage.currentIndexChanged.connect(self._stage_changed)
        self._form_row(layout, "音域の解放段階", self.stage)

        self.range_label = QLabel("")
        self.range_label.setObjectName("strongLabel")
        self._form_row(layout, "発音できる音域", self.range_label)

        self.correction = QCheckBox("音域外の音をオクターブ単位で音域内へ補正する")
        self.correction.setChecked(self.owner.range_correction)
        self.correction.toggled.connect(
            lambda value: self.owner.update_setting("range_correction", value)
        )
        layout.addWidget(self.correction)
        hint = QLabel("補正はフレーズ単位でまとめて移動します。オフなら音域外は従来どおり鳴りません。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("実際に鳴る通りのMIDIを書き出して確認できます"))
        export_row.addStretch()
        self.export_button = QPushButton("MIDIに書き出す")
        self.export_button.setObjectName("midiButton")
        self.export_button.setFixedSize(140, 30)
        self.export_button.clicked.connect(self.owner.export_audible_midi)
        export_row.addWidget(self.export_button)
        layout.addLayout(export_row)
        self._reload_stages()

    def _reload_stages(self) -> None:
        profile = instrument_profile(self.owner.instrument)
        self.stage.blockSignals(True)
        self.stage.clear()
        for step in profile.stages:
            self.stage.addItem(step.label)
        self.stage.setCurrentIndex(profile.clamp_stage(self.owner.unlock_stage))
        self.stage.setEnabled(len(profile.stages) > 1)
        self.stage.blockSignals(False)
        self._refresh_range_label()

    def _refresh_range_label(self) -> None:
        profile = instrument_profile(self.owner.instrument)
        low, high = profile.sounding_range(48, self.owner.unlock_stage)
        self.range_label.setText(f"{note_name(low)} - {note_name(high)}")

    def _instrument_changed(self, index: int) -> None:
        self.owner.update_setting("instrument", self.instrument.itemData(index))
        self._reload_stages()

    def _stage_changed(self, index: int) -> None:
        self.owner.update_setting("unlock_stage", index)
        self._refresh_range_label()


class ResonanceMidiWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.config = load_config()
        self.song: MidiSong | None = None
        self.windows: list[WindowInfo] = []
        self.options_window: OptionsWindow | None = None
        self.instrument_window: InstrumentWindow | None = None
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
        self.auto_octave = bool(self.config.get("auto_octave_switch", True))
        self.game_octave_offset = max(-3, min(3, int(self.config.get("game_octave_offset", 0))))
        self.countdown = max(0, min(10, int(self.config.get("countdown", 3))))
        self.sustain_check = bool(self.config.get("check_sustain_state", True))
        self.topmost = bool(self.config.get("topmost", False))
        self.opacity = max(0.5, min(1.0, float(self.config.get("opacity", 0.8))))
        self.ui_scale = max(0.5, min(2.0, round(float(self.config.get("ui_scale", 1.0)), 1)))
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
        self.instrument_button = self.icon_button(keyboard_icon(18), "楽器設定", 32)
        self.instrument_button.clicked.connect(self.open_instruments)
        self.gear_button = self.icon_button(gear_icon(18), "オプション", 32)
        self.gear_button.clicked.connect(self.open_options)
        self.close_button = self.icon_button(simple_icon("close", WHITE, 15), "閉じる", 32)
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.instrument_button)
        header_layout.addWidget(self.gear_button)
        header_layout.addWidget(self.close_button)
        body.addWidget(header)
        body.addSpacing(2)

        self.file_panel = self.panel()
        self.file_panel.setFixedHeight(57)
        file_layout = QHBoxLayout(self.file_panel)
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
        self.ui_scale = value
        self.config["ui_scale"] = value
        self.scale_widget_tree(self)
        if self.instrument_window is not None:
            self.scale_widget_tree(self.instrument_window)
        if self.options_window is not None:
            self.scale_widget_tree(self.options_window)
            self.options_window.scale_value.setText(f"{value:.1f}x")
            self.options_window.scale_slider.blockSignals(True)
            self.options_window.scale_slider.setValue(round(value * 10))
            self.options_window.scale_slider.blockSignals(False)
        self._keep_on_screen()
        self.anchor_options()
        self.save()

    def _keep_on_screen(self) -> None:
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left()), max(area.left(), area.right() - self.width() + 1))
        y = min(max(self.y(), area.top()), max(area.top(), area.bottom() - self.height() + 1))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def choose_file(self) -> None:
        last = Path(self.config.get("last_midi", ""))
        initial = str(last.parent) if last.parent.is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(self, "MIDIファイルを選択", initial, "MIDIファイル (*.mid *.midi);;すべてのファイル (*.*)")
        if path:
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
        self.song_title.setText(song.name)
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
        if not self.song:
            self.choose_file()
            return
        if (self.player.state == "playing" or self.countdown_timer.isActive()
                or self.sustain_check_pending):
            self.stop()
            return
        self.sync_player_config()
        target = self._focus_target()
        if self.sustain_check:
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
        if self.countdown <= 0:
            self.player.play()
        else:
            self.countdown_remaining = self.countdown
            self._show_countdown(self.countdown_remaining)
            self.countdown_timer.start()
        self._set_running(True)

    def stop(self) -> None:
        self.sustain_check_pending = False
        self.countdown_timer.stop()
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
        if self.options_window is not None:
            checkbox = self.options_window.sustain_check
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
        if not self.seeking:
            self.seek.setValue(round(position * 1000))
            self.current_time.setText(format_time(position))
        if state != "playing":
            self._set_running(False)

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
            f"音域補正で移動した音: {stats['folded_notes']}\n"
            f"鳴らないため除外した音: {dropped}",
        )

    def open_options(self) -> None:
        # Both panels occupy the same spot below the window, so opening one
        # always dismisses the other.
        if self.instrument_window is not None:
            self.instrument_window.close()
        if self.options_window is None:
            self.options_window = OptionsWindow(self)
            self.options_window.closed.connect(self._options_closed)
        self.anchor_options()
        self.options_window.show_front()

    def open_instruments(self) -> None:
        if self.options_window is not None:
            self.options_window.close()
        if self.instrument_window is None:
            self.instrument_window = InstrumentWindow(self)
            self.instrument_window.closed.connect(self._instrument_closed)
        self.anchor_options()
        self.instrument_window.show_front()

    def anchor_options(self) -> None:
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

    def _options_closed(self) -> None:
        if self.options_window is not None:
            self.options_window.deleteLater()
        self.options_window = None

    def _instrument_closed(self) -> None:
        if self.instrument_window is not None:
            self.instrument_window.deleteLater()
        self.instrument_window = None

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
        if self.player.keyboard_shifted:
            self._focus_target()
        self.player.close()
        self.save()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Resonance MIDI Player")
    app.setStyle("Fusion")
    window = ResonanceMidiWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
