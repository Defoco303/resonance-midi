import time
import unittest
from pathlib import Path

from midi_parser import MidiNote, MidiSong
from player import KEYBOARD_PATHS, KEYBOARD_STATES, MidiPlayer, next_keyboard_state


class PlayerTests(unittest.TestCase):
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

    def test_auto_octave_pulses_low_then_high_and_returns(self):
        sent = []
        song = MidiSong(
            Path("four-octaves.mid"), "four octaves", 0.08,
            (
                MidiNote(0.01, 0.06, 48, 100, 0, 0),  # C3 = Z normally
                MidiNote(0.01, 0.06, 84, 100, 0, 0),  # C6 = Z after >
            ),
            ("track",), 120,
        )
        mapping = {48: "Z"}
        player = MidiPlayer(lambda key, down: sent.append((key, down)),
                            lambda *_: None, lambda msg: self.fail(msg))
        try:
            player.configure(mapping, 0, 1.0, 30, auto_octave=True, octave_switch_ms=0)
            player.load(song)
            player.play()
            time.sleep(0.14)
            self.assertEqual(sent, [
                ("Z", True), ("Z", False),
                (".", True), (".", False),
                ("Z", True), ("Z", False),
                (",", True), (",", False),
            ])
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


if __name__ == "__main__":
    unittest.main()
