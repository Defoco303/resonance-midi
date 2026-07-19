from __future__ import annotations

import json
import os
from pathlib import Path


APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "ResonanceMidiPlayer"
CONFIG_PATH = APP_DIR / "config.json"

# Star Resonance JP: the three octaves simultaneously shown on the piano UI.
# The tuple is chromatic from C3 through B5 (white and black keys interleaved).
DEFAULT_KEYS = (
    "Z", "1", "X", "2", "C", "V", "3", "B", "4", "N", "5", "M",
    "A", "6", "S", "7", "D", "F", "8", "G", "9", "H", "0", "J",
    "Q", "-", "W", "^", "E", "R", "P", "T", "@", "Y", "[", "U",
)

TWO_OCTAVE_DEFAULT_KEYS = DEFAULT_KEYS[:24]

# Version 1 shipped with this provisional layout. It is retained only so an
# untouched saved config can be migrated without overwriting custom mappings.
OLD_DEFAULT_KEYS = (
    "Z", "S", "X", "D", "C", "V", "G", "B", "H", "N", "J", "M",
    "Q", "2", "W", "3", "E", "R", "5", "T", "6", "Y", "7", "U",
    "I", "9", "O", "0", "P", "[", "]", "L", ";", ",", ".", "/",
)


def default_mapping(base_note: int = 48) -> dict[int, str]:
    return {base_note + index: key for index, key in enumerate(DEFAULT_KEYS)}


DEFAULT_CONFIG = {
    "config_version": 9,
    "mapping": {str(note): key for note, key in default_mapping().items()},
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
    "target_title": "ブループロトコル：スターレゾナンス",
    "last_midi": "",
    "topmost": True,
    "opacity": 0.5,
    "window_x": None,
    "window_y": None,
}


def load_config() -> dict:
    result = dict(DEFAULT_CONFIG)
    result["mapping"] = dict(DEFAULT_CONFIG["mapping"])
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            old_mapping = {str(48 + index): key for index, key in enumerate(OLD_DEFAULT_KEYS)}
            if int(loaded.get("config_version", 1)) < 2 and loaded.get("mapping") == old_mapping:
                loaded["mapping"] = dict(DEFAULT_CONFIG["mapping"])
            two_octave_mapping = {
                str(48 + index): key for index, key in enumerate(TWO_OCTAVE_DEFAULT_KEYS)
            }
            if int(loaded.get("config_version", 1)) < 4 and loaded.get("mapping") == two_octave_mapping:
                loaded["mapping"] = dict(DEFAULT_CONFIG["mapping"])
            if loaded.get("target_title") in (None, "", "Star Resonance"):
                loaded["target_title"] = DEFAULT_CONFIG["target_title"]
            if int(loaded.get("config_version", 1)) < 7 and loaded.get("opacity", 1.0) == 1.0:
                loaded["opacity"] = 0.8
            loaded["config_version"] = 9
            result.update(loaded)
        if not isinstance(result.get("mapping"), dict):
            result["mapping"] = dict(DEFAULT_CONFIG["mapping"])
    except (OSError, ValueError, TypeError):
        pass
    return result


def save_config(config: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)


def mapping_for_game_octave(mapping: dict[int, str], octave_offset: int) -> dict[int, str]:
    """Shift expected pitches to match the game's currently displayed octave."""
    semitones = max(-3, min(3, int(octave_offset))) * 12
    return {note + semitones: key for note, key in mapping.items()
            if 0 <= note + semitones <= 127}
