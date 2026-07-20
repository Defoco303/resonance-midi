import tempfile
import unittest
from pathlib import Path

from midi_parser import MidiNote, load_midi
from midi_writer import write_midi


class MidiWriterTests(unittest.TestCase):
    def _round_trip(self, notes):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.mid"
            written = write_midi(path, notes)
            return written, load_midi(path)

    def test_notes_survive_a_round_trip(self):
        notes = [
            MidiNote(0.0, 0.5, 60, 100, 0, 0),
            MidiNote(0.5, 1.0, 64, 90, 0, 0),
            MidiNote(1.0, 2.0, 67, 80, 0, 0),
        ]
        written, song = self._round_trip(notes)
        self.assertEqual(written, 3)
        self.assertEqual([note.note for note in song.notes], [60, 64, 67])
        for original, result in zip(notes, sorted(song.notes, key=lambda n: n.start)):
            self.assertAlmostEqual(original.start, result.start, places=2)
            self.assertAlmostEqual(original.end, result.end, places=2)

    def test_tracks_are_kept_apart(self):
        notes = [MidiNote(0.0, 0.5, 60, 100, 0, 0), MidiNote(0.0, 0.5, 36, 100, 0, 1)]
        _, song = self._round_trip(notes)
        self.assertEqual(len({note.track for note in song.notes}), 2)

    def test_repeated_pitch_retriggers(self):
        # The note-off of the first must be written before the note-on of the
        # second, or the pair collapses into a single sounding note.
        notes = [MidiNote(0.0, 0.5, 60, 100, 0, 0), MidiNote(0.5, 1.0, 60, 100, 0, 0)]
        _, song = self._round_trip(notes)
        self.assertEqual(len(song.notes), 2)

    def test_empty_input_still_writes_a_valid_file(self):
        written, song = self._round_trip([])
        self.assertEqual(written, 0)
        self.assertEqual(len(song.notes), 0)


if __name__ == "__main__":
    unittest.main()
