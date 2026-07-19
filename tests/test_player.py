import time
import unittest
from pathlib import Path

from midi_parser import MidiNote, MidiSong
from player import MidiPlayer


class PlayerTests(unittest.TestCase):
    def test_playback_and_release(self):
        sent = []
        song = MidiSong(Path("test.mid"), "test", 0.08,
                        (MidiNote(0.01, 0.06, 60, 100, 0, 0),), ("track",), 120)
        player = MidiPlayer(lambda key, down: sent.append((key, down)), lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({60: "A"}, 0, 1.0, 30)
            player.load(song)
            player.play()
            time.sleep(0.12)
            self.assertEqual(sent, [("A", True), ("A", False)])
        finally:
            player.close()

    def test_natural_end_returns_position_to_start(self):
        positions = []
        song = MidiSong(Path("test.mid"), "test", 0.05,
                        (MidiNote(0.01, 0.03, 60, 100, 0, 0),), ("track",), 120)
        player = MidiPlayer(lambda *_: None, lambda pos, state: positions.append((pos, state)),
                            lambda msg: self.fail(msg))
        try:
            player.configure({60: "A"}, 0, 1.0, 10)
            player.load(song)
            player.play()
            time.sleep(0.10)
            self.assertEqual(player.position, 0.0)
            self.assertIn((0.0, "ended"), positions)
        finally:
            player.close()

    def test_seek_releases_key(self):
        sent = []
        song = MidiSong(Path("test.mid"), "test", 1.0,
                        (MidiNote(0.0, 0.9, 60, 100, 0, 0),), ("track",), 120)
        player = MidiPlayer(lambda key, down: sent.append((key, down)), lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({60: "A"}, 0, 1.0, 0)
            player.load(song)
            player.play()
            time.sleep(0.03)
            player.seek(0.95)
            self.assertIn(("A", False), sent)
        finally:
            player.close()

    def test_stop_preserves_current_position(self):
        positions = []
        song = MidiSong(Path("test.mid"), "test", 1.0,
                        (MidiNote(0.0, 0.9, 60, 100, 0, 0),), ("track",), 120)
        player = MidiPlayer(lambda *_: None, lambda pos, state: positions.append((pos, state)),
                            lambda msg: self.fail(msg))
        try:
            player.configure({60: "A"}, 0, 1.0, 30)
            player.load(song)
            player.seek(0.45)
            player.stop()
            self.assertAlmostEqual(player.position, 0.45)
            self.assertEqual(positions[-1], (0.45, "stopped"))
        finally:
            player.close()

    def test_auto_octave_pulses_low_then_high_and_returns(self):
        sent = []
        song = MidiSong(
            Path("four-octaves.mid"), "four octaves", 0.08,
            (
                MidiNote(0.01, 0.06, 83, 100, 0, 0),  # B5 = U normally
                MidiNote(0.01, 0.06, 84, 100, 0, 0),  # C6 = Z after >
            ),
            ("track",), 120,
        )
        mapping = {48: "Z", 83: "U"}
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(mapping, 0, 1.0, 30, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.14)
            self.assertEqual(sent, [
                ("U", True), ("U", False),
                (".", True), (".", False),
                ("Z", True), ("Z", False),
                (",", True), (",", False),
            ])
        finally:
            player.close()


if __name__ == "__main__":
    unittest.main()
