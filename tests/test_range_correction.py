import unittest

from midi_parser import MidiNote
from range_correction import fold_notes


def note(start: float, pitch: int, track: int = 0, channel: int = 0,
         length: float = 0.2) -> MidiNote:
    return MidiNote(start, start + length, pitch, 100, channel, track)


class RangeCorrectionTests(unittest.TestCase):
    # The keyboard's initial unlock: C3-B4.
    LOW, HIGH = 48, 71

    def test_part_that_fits_one_octave_down_moves_as_a_whole(self):
        notes = [note(index * 0.25, pitch)
                 for index, pitch in enumerate((72, 74, 76, 77))]
        shifts = fold_notes(notes, 0, self.LOW, self.HIGH)
        self.assertEqual(shifts, [-12, -12, -12, -12])

    def test_melody_crossing_the_boundary_does_not_zigzag(self):
        # Only C5 and D5 are out of range. Folding note by note would drop
        # them an octave below their neighbours and invert the contour.
        pitches = (69, 71, 72, 74, 71, 69)
        notes = [note(index * 0.1, pitch) for index, pitch in enumerate(pitches)]
        shifts = fold_notes(notes, 0, self.LOW, self.HIGH)
        self.assertEqual(len(set(shifts)), 1, "the phrase must move together")
        for pitch, shift in zip(pitches, shifts):
            self.assertTrue(self.LOW <= pitch + shift <= self.HIGH)

    def test_simultaneous_notes_keep_one_shift(self):
        notes = [note(0.0, pitch) for pitch in (60, 64, 67, 72)]
        shifts = fold_notes(notes, 0, self.LOW, self.HIGH)
        self.assertEqual(len(set(shifts)), 1, "a chord must not be split apart")

    def test_tracks_are_folded_independently(self):
        notes = [note(0.0, 74, track=0), note(0.25, 76, track=0),
                 note(0.0, 36, track=1), note(0.25, 38, track=1)]
        shifts = fold_notes(notes, 0, self.LOW, self.HIGH)
        self.assertEqual(shifts[:2], [-12, -12])  # melody comes down
        self.assertEqual(shifts[2:], [12, 12])    # bass goes up

    def test_notes_already_in_range_are_untouched(self):
        notes = [note(index * 0.25, pitch)
                 for index, pitch in enumerate((60, 62, 64, 65))]
        self.assertEqual(fold_notes(notes, 0, self.LOW, self.HIGH), [0, 0, 0, 0])

    def test_transpose_is_applied_before_folding(self):
        # +12 puts this note at 72, one semitone above the range.
        shifts = fold_notes([note(0.0, 60)], 12, self.LOW, self.HIGH)
        self.assertEqual(shifts, [-12])

    def test_chord_wider_than_the_range_falls_back_to_single_notes(self):
        notes = [note(0.0, 40), note(0.0, 100)]
        shifts = fold_notes(notes, 0, self.LOW, self.HIGH)
        for pitch, shift in zip((40, 100), shifts):
            self.assertTrue(self.LOW <= pitch + shift <= self.HIGH)


if __name__ == "__main__":
    unittest.main()
