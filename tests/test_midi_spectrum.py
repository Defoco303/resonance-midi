from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from midi_parser import MidiNote
from qt_app import MidiSpectrumWidget


class MidiSpectrumWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_held_note_lights_its_band(self) -> None:
        widget = MidiSpectrumWidget()
        widget.show()
        widget.set_notes([MidiNote(0.0, 1.0, 60, 127, 0, 0)])

        widget.set_position(0.05, True)
        widget._advance_frame()

        self.assertGreater(max(widget._levels), 0.5)
        widget.set_position(0.05, False)
        widget.close()

    def test_a0_through_c8_are_grouped_two_notes_per_bar(self) -> None:
        widget = MidiSpectrumWidget()

        self.assertEqual(widget._band_for(21), 0)
        self.assertEqual(widget._band_for(22), 0)
        self.assertEqual(widget._band_for(23), 1)
        self.assertEqual(widget._band_for(107), 43)
        self.assertEqual(widget._band_for(108), 43)

    def test_short_drum_hit_still_creates_a_visible_impulse(self) -> None:
        widget = MidiSpectrumWidget()
        widget.show()
        widget.set_notes([MidiNote(0.0, 0.008, 62, 100, 9, 0)])

        # Both attack and release occur between two 20 fps UI updates.
        widget.set_position(0.05, True)
        widget._advance_frame()

        self.assertGreater(max(widget._levels), 0.1)
        widget.set_position(0.05, False)
        widget.close()

    def test_large_seek_rebuilds_without_replaying_old_attacks(self) -> None:
        widget = MidiSpectrumWidget()
        widget.show()
        widget.set_notes([MidiNote(1.0, 1.2, 72, 127, 0, 0)])

        widget.set_position(5.0, True)

        self.assertEqual(max(widget._impulse), 0.0)
        self.assertEqual(max(widget._energy), 0.0)
        widget.set_position(5.0, False)
        widget.close()

    def test_widget_renders_offscreen(self) -> None:
        widget = MidiSpectrumWidget()
        widget.resize(480, 37)
        widget.show()
        widget.set_notes([
            MidiNote(0.0, 1.0, 36, 100, 0, 0),
            MidiNote(0.0, 1.0, 60, 110, 0, 0),
            MidiNote(0.0, 1.0, 84, 120, 0, 0),
        ])
        widget.set_position(0.05, True)
        widget._advance_frame()

        pixmap = QPixmap(widget.size())
        widget.render(pixmap)

        self.assertFalse(pixmap.isNull())
        widget.set_position(0.05, False)
        widget.close()


if __name__ == "__main__":
    unittest.main()
