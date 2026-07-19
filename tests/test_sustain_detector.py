import unittest

from PySide6.QtGui import QColor, QImage, QPainter

from sustain_detector import SustainState, detect_sustain_state


def make_game_image(width: int, height: int, state: SustainState) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(28, 34, 40))
    painter = QPainter(image)
    # Normal game detail outside the sustain-search band keeps the synthetic
    # capture distinguishable from a failed, uniformly black capture.
    painter.fillRect(0, 0, width, max(8, height // 20), QColor(90, 110, 125))
    if state is not SustainState.ABSENT:
        x = round(width * 0.54)
        y = round(height * 0.925)
        rect_width = round(width * 0.12)
        rect_height = max(8, round(height * 0.024))
        background = QColor(232, 232, 232) if state is SustainState.ON else QColor(62, 62, 62)
        foreground = QColor(35, 35, 35) if state is SustainState.ON else QColor(230, 230, 230)
        if state is SustainState.UNKNOWN:
            background = QColor(140, 140, 140)
            foreground = QColor(190, 190, 190)
        painter.fillRect(x, y, rect_width, rect_height, background)
        # Text-like strokes provide the same local contrast as the label
        # without depending on a particular installed Japanese font.
        stroke_y = y + max(2, rect_height // 3)
        for index in range(9):
            stroke_x = x + 5 + index * max(3, (rect_width - 10) // 10)
            painter.fillRect(stroke_x, stroke_y, 2, max(2, rect_height // 3), foreground)
    painter.end()
    return image


class SustainDetectorTests(unittest.TestCase):
    def test_detects_on_and_off_at_multiple_resolutions(self):
        for width, height in ((640, 480), (1920, 1080), (2560, 1440)):
            with self.subTest(size=(width, height), state="on"):
                self.assertIs(
                    detect_sustain_state(make_game_image(width, height, SustainState.ON)).state,
                    SustainState.ON,
                )
            with self.subTest(size=(width, height), state="off"):
                self.assertIs(
                    detect_sustain_state(make_game_image(width, height, SustainState.OFF)).state,
                    SustainState.OFF,
                )

    def test_reports_absent_label(self):
        result = detect_sustain_state(make_game_image(1280, 720, SustainState.ABSENT))
        self.assertIs(result.state, SustainState.ABSENT)

    def test_reports_uniform_capture_as_unknown(self):
        image = QImage(1280, 720, QImage.Format.Format_RGB32)
        image.fill(QColor(0, 0, 0))
        self.assertIs(detect_sustain_state(image).state, SustainState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
