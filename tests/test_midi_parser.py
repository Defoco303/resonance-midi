import tempfile
import unittest
from pathlib import Path

from midi_parser import load_midi, note_name


def vlq(value):
    result = [value & 0x7F]
    value >>= 7
    while value:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(result))


def make_midi():
    # 480 PPQ, C4 for one beat at 120 BPM, then E4 for one beat at 60 BPM.
    events = b"".join((
        vlq(0), b"\xff\x03\x04Test",
        vlq(0), b"\xff\x51\x03\x07\xa1\x20",
        vlq(0), b"\x90\x3c\x64",
        vlq(480), b"\x80\x3c\x00",
        vlq(0), b"\xff\x51\x03\x0f\x42\x40",
        vlq(0), b"\x90\x40\x50",
        vlq(480), b"\x80\x40\x00",
        vlq(0), b"\xff\x2f\x00",
    ))
    return b"MThd" + (6).to_bytes(4, "big") + b"\x00\x00\x00\x01\x01\xe0" + \
        b"MTrk" + len(events).to_bytes(4, "big") + events


class MidiParserTests(unittest.TestCase):
    def test_tempo_map_and_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tempo.mid"
            path.write_bytes(make_midi())
            song = load_midi(path)
        self.assertEqual(song.name, "Test")
        self.assertEqual(len(song.notes), 2)
        self.assertAlmostEqual(song.notes[0].start, 0.0)
        self.assertAlmostEqual(song.notes[0].end, 0.5)
        self.assertAlmostEqual(song.notes[1].start, 0.5)
        self.assertAlmostEqual(song.notes[1].end, 1.5)
        self.assertAlmostEqual(song.duration, 1.5)

    def test_note_names(self):
        self.assertEqual(note_name(60), "C4")
        self.assertEqual(note_name(69), "A4")


if __name__ == "__main__":
    unittest.main()
