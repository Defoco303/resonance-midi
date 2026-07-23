import json
import tempfile
import unittest
from pathlib import Path

import config_store


class ConfigStoreTests(unittest.TestCase):
    def test_distribution_defaults_match_release_profile(self):
        expected = {
            "speed": 1.0,
            "transpose": 0,
            "game_octave_offset": 0,
            "auto_octave_switch": True,
            "octave_switch_ms": 20,
            "press_ms": 1,
            "ignore_drums": True,
            "countdown": 3,
            "check_sustain_state": True,
            "ui_scale": 1.0,
            "topmost": True,
            "opacity": 0.5,
            "last_midi": "",
            "window_x": None,
            "window_y": None,
        }
        for key, value in expected.items():
            self.assertEqual(config_store.DEFAULT_CONFIG[key], value)

    def test_star_resonance_three_octave_layout(self):
        mapping = config_store.default_mapping()
        expected = {
            48: "Z", 49: "1", 50: "X", 51: "2", 52: "C", 53: "V",
            54: "3", 55: "B", 56: "4", 57: "N", 58: "5", 59: "M",
            60: "A", 61: "6", 62: "S", 63: "7", 64: "D", 65: "F",
            66: "8", 67: "G", 68: "9", 69: "H", 70: "0", 71: "J",
            72: "Q", 73: "I", 74: "W", 75: "O", 76: "E", 77: "R",
            78: "P", 79: "T", 80: "@", 81: "Y", 82: "[", 83: "U",
        }
        self.assertEqual(mapping, expected)

    def test_untouched_v1_mapping_is_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = config_store.CONFIG_PATH
            try:
                config_store.CONFIG_PATH = Path(folder) / "config.json"
                old_mapping = {str(48 + i): key for i, key in enumerate(config_store.OLD_DEFAULT_KEYS)}
                config_store.CONFIG_PATH.write_text(json.dumps({"mapping": old_mapping}), encoding="utf-8")
                loaded = config_store.load_config()
            finally:
                config_store.CONFIG_PATH = old_path
        self.assertEqual(loaded["mapping"], config_store.DEFAULT_CONFIG["mapping"])
        self.assertEqual(loaded["config_version"], 12)

    def test_untouched_two_octave_mapping_is_expanded(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = config_store.CONFIG_PATH
            try:
                config_store.CONFIG_PATH = Path(folder) / "config.json"
                mapping = {
                    str(48 + i): key
                    for i, key in enumerate(config_store.TWO_OCTAVE_DEFAULT_KEYS)
                }
                config_store.CONFIG_PATH.write_text(
                    json.dumps({"config_version": 3, "mapping": mapping}), encoding="utf-8")
                loaded = config_store.load_config()
            finally:
                config_store.CONFIG_PATH = old_path
        self.assertEqual(loaded["mapping"], config_store.DEFAULT_CONFIG["mapping"])
        self.assertEqual(loaded["config_version"], 12)

    def test_v6_default_opacity_is_migrated_to_eighty_percent(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = config_store.CONFIG_PATH
            try:
                config_store.CONFIG_PATH = Path(folder) / "config.json"
                config_store.CONFIG_PATH.write_text(
                    json.dumps({"config_version": 6, "opacity": 1.0}), encoding="utf-8")
                loaded = config_store.load_config()
            finally:
                config_store.CONFIG_PATH = old_path
        self.assertEqual(loaded["config_version"], 12)
        self.assertEqual(loaded["opacity"], 0.8)

    def test_incorrect_v9_black_keys_are_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = config_store.CONFIG_PATH
            try:
                config_store.CONFIG_PATH = Path(folder) / "config.json"
                wrong_mapping = {
                    str(48 + i): key
                    for i, key in enumerate(config_store.WRONG_V9_DEFAULT_KEYS)
                }
                config_store.CONFIG_PATH.write_text(
                    json.dumps({"config_version": 9, "mapping": wrong_mapping}), encoding="utf-8")
                loaded = config_store.load_config()
            finally:
                config_store.CONFIG_PATH = old_path
        self.assertEqual(loaded["mapping"], config_store.DEFAULT_CONFIG["mapping"])
        self.assertEqual(loaded["config_version"], 12)

    def test_game_octave_changes_effective_pitch(self):
        mapping = {48: "Z", 60: "A"}
        self.assertEqual(config_store.mapping_for_game_octave(mapping, 1), {60: "Z", 72: "A"})
        self.assertEqual(config_store.mapping_for_game_octave(mapping, -3), {12: "Z", 24: "A"})

    def test_old_window_title_is_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = config_store.CONFIG_PATH
            try:
                config_store.CONFIG_PATH = Path(folder) / "config.json"
                config_store.CONFIG_PATH.write_text(
                    json.dumps({"config_version": 2, "target_title": "Star Resonance"}), encoding="utf-8")
                loaded = config_store.load_config()
            finally:
                config_store.CONFIG_PATH = old_path
        self.assertEqual(loaded["target_title"], "ブループロトコル：スターレゾナンス")


if __name__ == "__main__":
    unittest.main()
