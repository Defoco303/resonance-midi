import unittest

from instruments import (
    DRUM_GM_OFFSETS,
    NORMAL_FIRST_NOTE,
    drum_note_for_gm,
)


class DrumMappingTests(unittest.TestCase):
    # The nine confirmed game drum keys as C3-window note numbers (C3 = 48).
    CLOSED_HH = 62  # S  D4
    BASS = 65       # F  F4
    FLOOR_TOM = 69  # H  A4
    SNARE = 72      # Q  C5
    MID_TOM = 74    # W  D5
    HIGH_TOM = 76   # E  E5
    CRASH = 77      # R  F5
    OPEN_HH = 79    # T  G5
    RIDE = 81       # Y  A5

    def test_every_target_is_one_of_the_nine_keys(self):
        valid = {
            self.CLOSED_HH, self.BASS, self.FLOOR_TOM, self.SNARE, self.MID_TOM,
            self.HIGH_TOM, self.CRASH, self.OPEN_HH, self.RIDE,
        }
        for gm in DRUM_GM_OFFSETS:
            self.assertIn(drum_note_for_gm(gm), valid, f"GM {gm} maps outside the 9 keys")

    def test_kit_pieces_map_to_expected_keys(self):
        cases = {
            35: self.BASS, 36: self.BASS,
            37: self.SNARE, 38: self.SNARE, 39: self.SNARE, 40: self.SNARE,
            41: self.FLOOR_TOM, 43: self.FLOOR_TOM,
            42: self.CLOSED_HH, 44: self.CLOSED_HH,
            45: self.MID_TOM, 47: self.MID_TOM,
            48: self.HIGH_TOM, 50: self.HIGH_TOM,
            46: self.OPEN_HH,
            49: self.CRASH, 52: self.CRASH, 55: self.CRASH, 57: self.CRASH,
            51: self.RIDE, 53: self.RIDE, 59: self.RIDE,
        }
        for gm, expected in cases.items():
            self.assertEqual(drum_note_for_gm(gm), expected, f"GM {gm}")

    def test_hi_mid_tom_is_the_high_tom(self):
        # User decision 2026-07-23: 48 counts as high, not mid.
        self.assertEqual(drum_note_for_gm(48), self.HIGH_TOM)

    def test_tambourine_and_cowbell_are_redirected_not_dropped(self):
        self.assertEqual(drum_note_for_gm(54), self.OPEN_HH)  # tambourine
        self.assertEqual(drum_note_for_gm(56), self.RIDE)     # cowbell

    def test_hand_percussion_maps_by_timbre(self):
        cases = {
            60: self.HIGH_TOM, 61: self.MID_TOM,          # bongos
            62: self.HIGH_TOM, 63: self.HIGH_TOM, 64: self.MID_TOM,  # congas
            65: self.HIGH_TOM, 66: self.MID_TOM,          # timbales
            67: self.RIDE, 68: self.RIDE,                 # agogos
            69: self.CLOSED_HH, 70: self.CLOSED_HH,       # cabasa, maracas
            73: self.CLOSED_HH, 74: self.OPEN_HH,         # guiros (short/long)
            75: self.SNARE,                               # claves
            76: self.HIGH_TOM, 77: self.MID_TOM,          # wood blocks
            80: self.RIDE, 81: self.RIDE,                 # triangles
        }
        for gm, expected in cases.items():
            self.assertEqual(drum_note_for_gm(gm), expected, f"GM {gm}")

    def test_effects_without_a_drum_voice_are_dropped(self):
        # Vibraslap, whistles, cuica: no close kit voice, left silent on purpose.
        for gm in (58, 71, 72, 78, 79):
            self.assertIsNone(drum_note_for_gm(gm), f"GM {gm} should be silent")

    def test_out_of_range_numbers_are_dropped(self):
        for gm in (0, 34, 82, 108):
            self.assertIsNone(drum_note_for_gm(gm))

    def test_full_unlock_stage_makes_no_redirects(self):
        # Stage 2 (default) is fully unlocked: cymbals/hats stay themselves.
        self.assertEqual(drum_note_for_gm(36, stage=2), self.BASS)
        self.assertEqual(drum_note_for_gm(42, stage=2), self.CLOSED_HH)
        self.assertEqual(drum_note_for_gm(46, stage=2), self.OPEN_HH)
        self.assertEqual(drum_note_for_gm(49, stage=2), self.CRASH)
        self.assertEqual(drum_note_for_gm(51, stage=2), self.RIDE)

    def test_initial_stage_redirects_locked_sounds(self):
        # Stage 0: only snare + 3 toms exist.
        self.assertEqual(drum_note_for_gm(36, stage=0), self.FLOOR_TOM)   # bass -> floor tom
        self.assertEqual(drum_note_for_gm(42, stage=0), self.HIGH_TOM)    # closed hh -> high tom
        self.assertEqual(drum_note_for_gm(46, stage=0), self.HIGH_TOM)    # open hh -> high tom
        self.assertEqual(drum_note_for_gm(51, stage=0), self.HIGH_TOM)    # ride -> high tom
        self.assertEqual(drum_note_for_gm(49, stage=0), self.SNARE)       # crash -> snare
        # Sounds that already exist are untouched.
        self.assertEqual(drum_note_for_gm(38, stage=0), self.SNARE)
        self.assertEqual(drum_note_for_gm(48, stage=0), self.HIGH_TOM)

    def test_stage_one_unlocks_bass_and_closed_hat(self):
        # Stage 1 adds bass + closed hi-hat; open hh / crash / ride still locked.
        self.assertEqual(drum_note_for_gm(36, stage=1), self.BASS)        # bass now itself
        self.assertEqual(drum_note_for_gm(42, stage=1), self.CLOSED_HH)   # closed hh now itself
        self.assertEqual(drum_note_for_gm(46, stage=1), self.CLOSED_HH)   # open hh -> closed hh
        self.assertEqual(drum_note_for_gm(51, stage=1), self.CLOSED_HH)   # ride -> closed hh
        self.assertEqual(drum_note_for_gm(49, stage=1), self.SNARE)       # crash -> snare

    def test_no_redirect_drops_locked_sounds(self):
        # Correction off: a locked sound is silent instead of being redirected;
        # an already-unlocked sound still plays.
        self.assertIsNone(drum_note_for_gm(36, stage=0, redirect=False))   # bass locked
        self.assertIsNone(drum_note_for_gm(49, stage=0, redirect=False))   # crash locked
        self.assertEqual(drum_note_for_gm(38, stage=0, redirect=False), self.SNARE)
        self.assertIsNone(drum_note_for_gm(46, stage=1, redirect=False))   # open hh locked at 1
        self.assertEqual(drum_note_for_gm(42, stage=1, redirect=False), self.CLOSED_HH)
        # Full unlock: redirect flag makes no difference.
        self.assertEqual(drum_note_for_gm(49, stage=2, redirect=False), self.CRASH)

    def test_first_note_shifts_the_target(self):
        # A +12 game_octave_offset moves C3 to 60; targets follow.
        self.assertEqual(drum_note_for_gm(38, first_note=60), self.SNARE + 12)
        self.assertEqual(drum_note_for_gm(38, first_note=NORMAL_FIRST_NOTE), self.SNARE)


if __name__ == "__main__":
    unittest.main()
