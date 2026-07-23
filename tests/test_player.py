import time
import unittest
from pathlib import Path

from midi_parser import MidiNote, MidiSong
from player import KEYBOARD_PATHS, KEYBOARD_STATES, MidiPlayer, next_keyboard_state


class PlayerTests(unittest.TestCase):
    def test_low_bank_starts_at_a0_on_n_key(self):
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            mapping = {
                48: "Z", 49: "1", 50: "X", 51: "2", 52: "C", 53: "V",
                54: "3", 55: "B", 56: "4", 57: "N", 58: "5", 59: "M",
            }
            player.configure(mapping, 0, 1.0, 1, auto_octave=True, octave_switch_ms=0)
            low = player._state_mappings[(-3, 0)]
            self.assertNotIn(20, low)  # G#0 and below do not exist.
            self.assertEqual(low[21], "N")  # A0
            self.assertEqual(low[22], "5")  # A#0
            self.assertEqual(low[23], "M")  # B0
        finally:
            player.close()

    def test_high_bank_ends_at_c8_on_q_key(self):
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            mapping = {
                48: "Z", 60: "A", 72: "Q", 73: "I",
            }
            player.configure(mapping, 0, 1.0, 1, auto_octave=True, octave_switch_ms=0)
            high = player._state_mappings[(3, 0)]
            self.assertEqual(high[84], "Z")   # C6
            self.assertEqual(high[96], "A")   # C7
            self.assertEqual(high[108], "Q")  # C8
            self.assertNotIn(109, high)         # C#8 and above do not exist.
        finally:
            player.close()

    def test_c8_note_moves_high_and_plays_q(self):
        sent = []
        song = MidiSong(
            Path("c8.mid"), "C8", 0.18,
            (MidiNote(0.10, 0.12, 108, 100, 0, 0),),
            ("track",), 120,
        )
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({48: "Z", 60: "A", 72: "Q"}, 0, 1.0, 1,
                             auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.24)
            self.assertIn((".", True), sent)
            self.assertIn(("Q", True), sent)
            self.assertIn(("Q", False), sent)
        finally:
            player.close()

    def test_notes_above_c8_are_ignored_without_moving_keyboard(self):
        sent = []
        song = MidiSong(
            Path("above-c8.mid"), "above C8", 0.08,
            (MidiNote(0.01, 0.03, 109, 100, 0, 0),),
            ("track",), 120,
        )
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({48: "Z", 72: "Q", 73: "I"}, 0, 1.0, 1,
                             auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.12)
            self.assertEqual(sent, [])
        finally:
            player.close()

    def test_a0_note_moves_low_and_plays_n(self):
        sent = []
        song = MidiSong(
            Path("a0.mid"), "A0", 0.18,
            (MidiNote(0.10, 0.12, 21, 100, 0, 0),),
            ("track",), 120,
        )
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            mapping = {
                48: "Z", 49: "1", 50: "X", 51: "2", 52: "C", 53: "V",
                54: "3", 55: "B", 56: "4", 57: "N", 58: "5", 59: "M",
            }
            player.configure(mapping, 0, 1.0, 1, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.24)
            self.assertIn((",", True), sent)
            self.assertIn(("N", True), sent)
            self.assertIn(("N", False), sent)
        finally:
            player.close()

    def test_notes_below_a0_are_ignored_without_moving_keyboard(self):
        sent = []
        song = MidiSong(
            Path("below-a0.mid"), "below A0", 0.08,
            (MidiNote(0.01, 0.03, 20, 100, 0, 0),),
            ("track",), 120,
        )
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({48: "Z", 57: "N"}, 0, 1.0, 1,
                             auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.12)
            self.assertEqual(sent, [])
        finally:
            player.close()

    def test_low_and_normal_chord_is_split_and_returns_to_initial_view(self):
        sent = []
        song = MidiSong(
            Path("a0-c3.mid"), "A0 plus C3", 0.10,
            (
                MidiNote(0.01, 0.04, 21, 100, 0, 0),
                MidiNote(0.01, 0.04, 48, 100, 0, 0),
            ),
            ("track",), 120,
        )
        mapping = {
            48: "Z", 49: "1", 50: "X", 51: "2", 52: "C", 53: "V",
            54: "3", 55: "B", 56: "4", 57: "N", 58: "5", 59: "M",
        }
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(mapping, 0, 1.0, 1, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            self.assertEqual(player.octave_plan_stats["pulse_batches"], 1)
            player.play()
            time.sleep(0.18)
            self.assertIn(("Z", True), sent)
            self.assertIn((",", True), sent)
            self.assertIn(("N", True), sent)
            self.assertIn((".", True), sent)
            self.assertFalse(player.keyboard_shifted)
        finally:
            player.close()

    def test_a0_and_c8_chord_visits_both_outer_banks_and_returns(self):
        sent = []
        song = MidiSong(
            Path("a0-c8.mid"), "A0 plus C8", 0.12,
            (
                MidiNote(0.01, 0.04, 21, 100, 0, 0),
                MidiNote(0.01, 0.04, 108, 100, 0, 0),
            ),
            ("track",), 120,
        )
        mapping = {
            48: "Z", 57: "N", 60: "A", 72: "Q",
        }
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(mapping, 0, 1.0, 1, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            self.assertEqual(player.octave_plan_stats["pulse_batches"], 1)
            self.assertEqual(player.octave_plan_stats["control_taps"], 4)
            player.play()
            time.sleep(0.20)
            self.assertIn(("N", True), sent)
            self.assertIn(("Q", True), sent)
            self.assertEqual(sum(key == "." and down for key, down in sent), 2)
            self.assertEqual(sum(key == "," and down for key, down in sent), 2)
            self.assertFalse(player.keyboard_shifted)
        finally:
            player.close()

    def test_game_keyboard_state_rules(self):
        normal = (0, 0)
        shifted = next_keyboard_state(normal, "LSHIFT")
        self.assertEqual(shifted, (0, 1))
        self.assertEqual(next_keyboard_state(shifted, "LCTRL"), (0, -1))
        self.assertEqual(next_keyboard_state((0, -1), "LSHIFT"), (0, 1))
        low_shifted = next_keyboard_state(shifted, ",")
        self.assertEqual(low_shifted, (-3, 1))
        self.assertEqual(next_keyboard_state(low_shifted, "LSHIFT"), (-3, 0))
        self.assertEqual(next_keyboard_state((-3, 0), "LCTRL"), (-3, 0))
        self.assertEqual(next_keyboard_state((3, 0), "LSHIFT"), (3, 0))

    def test_all_planned_keyboard_paths_reach_their_target(self):
        for start in KEYBOARD_STATES:
            for target in KEYBOARD_STATES:
                with self.subTest(start=start, target=target):
                    state = start
                    for control in KEYBOARD_PATHS[(start, target)]:
                        next_state = next_keyboard_state(state, control)
                        self.assertNotEqual(next_state, state)
                        state = next_state
                    self.assertEqual(state, target)

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

    def test_pulse_holds_both_notes_through_the_bank_visit(self):
        sent = []
        song = MidiSong(
            Path("four-octaves.mid"), "four octaves", 0.10,
            (
                MidiNote(0.01, 0.06, 48, 100, 0, 0),  # C3 = Z in the middle window
                MidiNote(0.01, 0.06, 86, 100, 0, 0),  # D6 = X after > (no key clash)
            ),
            ("track",), 120,
        )
        mapping = {48: "Z", 50: "X"}
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(mapping, 0, 1.0, 30, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            self.assertEqual(player.octave_plan_stats["pulse_batches"], 1)
            player.play()
            time.sleep(0.16)
            # Both notes are struck; neither key collides with the other.
            self.assertIn(("Z", True), sent)
            self.assertIn(("X", True), sent)
            # C3 (Z) is held THROUGH the pulse: the > and < happen before Z is
            # released, and its release comes at the note-off, not at the switch.
            z_up = sent.index(("Z", False))
            self.assertIn((".", True), sent[:z_up])
            self.assertIn((",", True), sent[:z_up])
            self.assertFalse(player.keyboard_shifted)
        finally:
            player.close()

    def test_auto_octave_plans_shift_for_high_run(self):
        sent = []
        song = MidiSong(
            Path("high-run.mid"), "high run", 0.20,
            (
                MidiNote(0.01, 0.015, 48, 100, 0, 0),
                MidiNote(0.04, 0.045, 84, 100, 0, 0),
                MidiNote(0.07, 0.075, 86, 100, 0, 0),
                MidiNote(0.10, 0.105, 88, 100, 0, 0),
                MidiNote(0.14, 0.145, 48, 100, 0, 0),
            ),
            ("track",), 120,
        )
        mapping = {
            48: "Z", 50: "X", 52: "C",
            72: "Q", 74: "W", 76: "E",
        }
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(mapping, 0, 1.0, 1, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            self.assertEqual(player.octave_plan_stats, {
                "shift_taps": 2,
                "pulse_batches": 0,
                "control_taps": 2,
            })
            player.play()
            time.sleep(0.25)
            controls = [item for item in sent if item[0] in ("LSHIFT", ".", ",")]
            self.assertEqual(controls, [
                ("LSHIFT", True), ("LSHIFT", False),
                ("LSHIFT", True), ("LSHIFT", False),
            ])
        finally:
            player.close()

    def test_seek_countdown_prepares_next_attack_view_before_play(self):
        sent = []
        song = MidiSong(
            Path("seek-prepare.mid"), "seek prepare", 1.0,
            (MidiNote(0.60, 0.70, 84, 100, 0, 0),),
            ("track",), 120,
        )
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({48: "Z", 72: "Q"}, 0, 1.0, 1,
                             auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.seek(0.60)
            player.prepare_for_playback()
            self.assertEqual(sent, [("LSHIFT", True), ("LSHIFT", False)])
            self.assertEqual(player.state, "stopped")
            self.assertTrue(player.keyboard_shifted)
        finally:
            player.close()

    def test_range_change_uses_rest_and_preserves_real_key_hold(self):
        sent = []
        started = time.perf_counter()

        def sender(key, down):
            sent.append((time.perf_counter() - started, key, down))

        song = MidiSong(
            Path("rest-before-high.mid"), "rest before high", 0.30,
            (
                MidiNote(0.02, 0.03, 48, 100, 0, 0),
                MidiNote(0.18, 0.181, 84, 100, 0, 0),
            ),
            ("track",), 120,
        )
        player = MidiPlayer(sender, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({48: "Z", 72: "Q"}, 0, 1.0, 1,
                             auto_octave=True, octave_switch_ms=20)
            player.load(song)
            started = time.perf_counter()
            player.play()
            time.sleep(0.26)
            shift_up = next(t for t, key, down in sent if key == "LSHIFT" and not down)
            high_down = next(t for t, key, down in sent if key == "Q" and down)
            high_up = next(t for t, key, down in sent if key == "Q" and not down)
            self.assertLess(shift_up, high_down - 0.010)
            self.assertGreaterEqual(high_up - high_down, 0.0075)
        finally:
            player.close()

    def test_seek_restores_shifted_keyboard(self):
        sent = []
        song = MidiSong(
            Path("seek-high.mid"), "seek high", 1.0,
            (MidiNote(0.01, 0.50, 84, 100, 0, 0),),
            ("track",), 120,
        )
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure({48: "Z", 72: "Q"}, 0, 1.0, 100,
                             auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.05)
            self.assertTrue(player.keyboard_shifted)
            player.seek(0.80)
            self.assertFalse(player.keyboard_shifted)
            controls = [item for item in sent if item[0] == "LSHIFT"]
            self.assertEqual(controls, [
                ("LSHIFT", True), ("LSHIFT", False),
                ("LSHIFT", True), ("LSHIFT", False),
            ])
        finally:
            player.close()


class InstrumentRangeTests(unittest.TestCase):
    MAPPING = {48: "Z", 60: "A", 72: "Q"}

    def _song(self, *pitches: int) -> MidiSong:
        notes = tuple(
            MidiNote(0.10 + index * 0.02, 0.14 + index * 0.02, pitch, 100, 0, 0)
            for index, pitch in enumerate(pitches)
        )
        return MidiSong(Path("stage.mid"), "stage", 0.4, notes, ("track",), 120)

    def _play(self, pitches, stage, correction, auto=False):
        sent = []
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(self.MAPPING, 0, 1.0, 1, auto_octave=auto,
                             octave_switch_ms=0, instrument="keyboard",
                             unlock_stage=stage, range_correction=correction)
            player.load(self._song(*pitches))
            stats = player.range_stats
            player.play()
            time.sleep(0.35)
            return sent, stats
        finally:
            player.close()

    def test_initial_unlock_silences_notes_above_b4(self):
        # C6 is inside the physical keyboard but grey until achievement 1.
        sent, stats = self._play((84,), stage=0, correction=False)
        self.assertEqual(sent, [])
        self.assertEqual(stats["unplayable_notes"], 1)
        self.assertEqual(stats["folded_notes"], 0)

    def test_range_correction_folds_c6_into_the_initial_unlock(self):
        sent, stats = self._play((84,), stage=0, correction=True)
        self.assertIn(("A", True), sent)  # C6 lands on C4
        self.assertEqual(stats["unplayable_notes"], 0)
        self.assertEqual(stats["folded_notes"], 1)

    def test_full_unlock_reaches_c6_through_the_high_bank(self):
        sent, stats = self._play((84,), stage=3, correction=True, auto=True)
        self.assertEqual(stats["folded_notes"], 0)  # nothing to correct
        self.assertEqual(stats["unplayable_notes"], 0)
        # One Shift is cheaper than >, and C6 is Q in the C4-B6 view.
        self.assertIn(("LSHIFT", True), sent)
        self.assertIn(("Q", True), sent)

    def test_audible_notes_report_the_pitch_that_will_sound(self):
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(self.MAPPING, 0, 1.0, 1, auto_octave=False,
                             unlock_stage=0, range_correction=True)
            player.load(self._song(84))  # C6, folded down to C4
            self.assertEqual([note.note for note in player.audible_notes], [60])
        finally:
            player.close()

    def test_audible_notes_drop_what_cannot_be_reached(self):
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(self.MAPPING, 0, 1.0, 1, auto_octave=False,
                             unlock_stage=0, range_correction=False)
            player.load(self._song(84))
            self.assertEqual(player.audible_notes, [])
        finally:
            player.close()

    def test_audible_notes_include_the_transpose(self):
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(self.MAPPING, 12, 1.0, 1, auto_octave=False,
                             unlock_stage=3, range_correction=False)
            player.load(self._song(48))  # C3 +12 lands on the mapped C4
            self.assertEqual([note.note for note in player.audible_notes], [60])
        finally:
            player.close()

    def test_bass_profile_starts_in_the_left_window(self):
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(self.MAPPING, 0, 1.0, 1, instrument="bass")
            self.assertEqual(player._initial_state, (-3, 0))
            self.assertFalse(player.keyboard_shifted)
        finally:
            player.close()


class DrumPlaybackTests(unittest.TestCase):
    # The full C3-B5 layout so the nine drum keys resolve to real letters.
    from config_store import default_mapping as _dm
    MAPPING = _dm()

    def _drum_song(self, *events):
        # events: (start, gm_note) tuples on the percussion channel (9).
        notes = tuple(
            MidiNote(start, start + 0.01, gm, 100, 9, 0)
            for start, gm in events
        )
        end = max(start for start, _ in events) + 0.1
        return MidiSong(Path("drum.mid"), "drum", end, notes, ("track",), 120)

    def _player(self, sent, **kw):
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        player.configure(self.MAPPING, kw.pop("transpose", 0), 1.0, 1,
                         instrument="drums", **kw)
        return player

    def test_gm_percussion_plays_the_nine_fixed_drum_keys(self):
        sent = []
        player = self._player(sent, auto_octave=True, octave_switch_ms=0)
        try:
            player.load(self._drum_song(
                (0.02, 36),  # bass drum -> F
                (0.05, 38),  # snare -> Q
                (0.08, 42),  # closed hi-hat -> S
                (0.11, 46),  # open hi-hat -> T
                (0.14, 49),  # crash -> R
                (0.17, 51),  # ride -> Y
                (0.20, 48),  # hi-mid tom -> E (high tom, user decision)
                (0.23, 54),  # tambourine -> T (redirected)
                (0.26, 56),  # cowbell -> Y (redirected)
            ))
            # Drums sit entirely in the middle window: no switching at all.
            self.assertEqual(player.octave_plan_stats["control_taps"], 0)
            self.assertEqual(player.octave_plan_stats["pulse_batches"], 0)
            player.play()
            time.sleep(0.4)
            pressed = [key for key, down in sent if down]
            self.assertEqual(pressed, ["F", "Q", "S", "T", "R", "Y", "E", "T", "Y"])
        finally:
            player.close()

    def test_unmapped_percussion_is_dropped_and_counted(self):
        sent = []
        player = self._player(sent)
        try:
            player.load(self._drum_song((0.02, 38), (0.05, 71)))  # snare + short whistle
            self.assertEqual(player.range_stats["unplayable_notes"], 1)
            self.assertEqual([n.note for n in player.audible_notes], [72])  # snare only
        finally:
            player.close()

    def test_initial_drum_stage_redirects_locked_sounds_with_correction(self):
        sent = []
        # Correction on: locked sounds are redirected. Only snare + toms unlocked.
        player = self._player(sent, unlock_stage=0, range_correction=True)
        try:
            # bass(36)->floor tom H(69), crash(49)->snare Q(72), closed hh(42)->high tom E(76)
            player.load(self._drum_song((0.02, 36), (0.05, 49), (0.08, 42)))
            self.assertEqual([n.note for n in player.audible_notes], [69, 72, 76])
        finally:
            player.close()

    def test_locked_drums_are_dropped_without_correction(self):
        sent = []
        # Correction off (default): locked sounds go silent instead of moving.
        player = self._player(sent, unlock_stage=0)
        try:
            # bass + crash locked -> dropped; snare(38) unlocked -> Q(72).
            player.load(self._drum_song((0.02, 36), (0.05, 49), (0.08, 38)))
            self.assertEqual([n.note for n in player.audible_notes], [72])
            self.assertEqual(player.range_stats["unplayable_notes"], 2)
        finally:
            player.close()

    def test_melodic_channels_are_ignored_in_drum_mode(self):
        sent = []
        player = self._player(sent)
        try:
            song = MidiSong(
                Path("mixed.mid"), "mixed", 0.3,
                (MidiNote(0.02, 0.03, 60, 100, 0, 0),   # melody, channel 0
                 MidiNote(0.05, 0.06, 38, 100, 9, 0)),  # snare, channel 9
                ("track",), 120,
            )
            player.load(song)
            self.assertEqual([n.note for n in player.audible_notes], [72])
        finally:
            player.close()

    def test_transpose_does_not_shift_drums(self):
        sent = []
        player = self._player(sent, transpose=12)
        try:
            player.load(self._drum_song((0.02, 38)))  # snare stays on Q (72)
            self.assertEqual([n.note for n in player.audible_notes], [72])
        finally:
            player.close()


class NaturalDecayTests(unittest.TestCase):
    def test_natural_decay_flags(self):
        from instruments import instrument_profile
        # Piano is on trial as natural-decay too (relies on the sustain pedal).
        self.assertTrue(instrument_profile("keyboard").natural_decay)
        self.assertTrue(instrument_profile("guitar").natural_decay)
        self.assertTrue(instrument_profile("bass").natural_decay)
        self.assertFalse(instrument_profile("drums").natural_decay)

    def _first_note_off(self, instrument: str, press_ms: int) -> float:
        from config_store import default_mapping
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(default_mapping(), 0, 1.0, press_ms, instrument=instrument)
            song = MidiSong(Path("d.mid"), "d", 1.0,
                            (MidiNote(0.0, 0.5, 64, 100, 0, 0),), ("t",), 120)  # E4, 0.5s
            player.load(song)
            return next(e.time for e in player._events if not e.pressed)
        finally:
            player.close()

    def test_natural_decay_holds_full_note_despite_short_press_ms(self):
        # Held for the whole note even with press_ms=1, so the user never tunes
        # key-hold per instrument; the octave planner frees the key when needed.
        self.assertAlmostEqual(self._first_note_off("guitar", 1), 0.5, places=3)
        self.assertAlmostEqual(self._first_note_off("keyboard", 1), 0.5, places=3)


class HoldThroughSwitchTests(unittest.TestCase):
    def test_repeated_note_releases_before_the_next_hit(self):
        from config_store import default_mapping
        player = MidiPlayer(lambda *_: None, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(default_mapping(), 0, 1.0, 0, instrument="keyboard")
            # Two legato repeats of C4; full-hold would merge them without a gap.
            song = MidiSong(
                Path("rep.mid"), "rep", 0.6,
                (MidiNote(0.0, 0.25, 60, 100, 0, 0), MidiNote(0.25, 0.50, 60, 100, 0, 0)),
                ("t",), 120,
            )
            player.load(song)
            offs = sorted(e.time for e in player._events if not e.pressed)
            # First note is released before the repeat, leaving a re-trigger gap.
            self.assertLessEqual(offs[0], 0.25 - 0.029)
            # A single (non-repeated) note still holds the full duration.
            player.load(MidiSong(Path("one.mid"), "one", 0.6,
                                 (MidiNote(0.0, 0.25, 60, 100, 0, 0),), ("t",), 120))
            self.assertAlmostEqual(
                next(e.time for e in player._events if not e.pressed), 0.25, places=3)
        finally:
            player.close()

    def test_held_note_survives_an_octave_switch(self):
        from config_store import default_mapping
        sent = []
        started = time.perf_counter()

        def send(key, down):
            sent.append((time.perf_counter() - started, key, down))

        # C3 (Z) held 0.0-0.30 while D6 at 0.14 forces a window switch (LSHIFT).
        song = MidiSong(
            Path("hts.mid"), "hts", 0.5,
            (MidiNote(0.0, 0.30, 48, 100, 0, 0), MidiNote(0.14, 0.16, 86, 100, 0, 0)),
            ("t",), 120,
        )
        player = MidiPlayer(send, lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(default_mapping(), 0, 1.0, 0, auto_octave=True,
                             octave_switch_ms=20, instrument="keyboard")
            player.load(song)
            started = time.perf_counter()
            player.play()
            time.sleep(0.5)
            shift_down = next(t for t, k, d in sent if k == "LSHIFT" and d)
            z_up = next(t for t, k, d in sent if k == "Z" and not d)
            w_down = next(t for t, k, d in sent if k == "W" and d)
            # C3's key is not released at the switch; it rings until its own end.
            self.assertGreater(z_up, shift_down + 0.10)
            # The switched-to note still lands on time.
            self.assertLess(abs(w_down - 0.14), 0.04)
        finally:
            player.close()


if __name__ == "__main__":
    unittest.main()
