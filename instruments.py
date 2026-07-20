"""Per-instrument keyboard profiles and achievement unlock stages.

The game shows one three-octave window at a time and every instrument shares
the same absolute pitch grid, so the physical key layout (``DEFAULT_KEYS``)
and the state-mapping generation in ``player`` are instrument independent.
What differs is where the window starts and how much of it actually sounds.

All offsets below are semitones relative to the C3 that starts the normal
view, so they survive the ``game_octave_offset`` remapping in ``config_store``.
"""

from __future__ import annotations

from dataclasses import dataclass


KeyboardState = tuple[int, int]  # (three-octave base bank, octave modifier)

# The normal view starts here; every offset in this module is relative to it.
NORMAL_FIRST_NOTE = 48  # C3


@dataclass(frozen=True)
class UnlockStage:
    """One achievement step. Ranges are cumulative and strictly ordered."""

    label: str
    low_offset: int
    high_offset: int


@dataclass(frozen=True)
class InstrumentProfile:
    key: str
    label: str
    initial_state: KeyboardState
    stages: tuple[UnlockStage, ...]
    selectable: bool
    note: str = ""

    def clamp_stage(self, stage: int) -> int:
        return max(0, min(int(stage), len(self.stages) - 1))

    def sounding_range(self, first_note: int, stage: int) -> tuple[int, int]:
        """Return the inclusive MIDI range that actually produces sound."""
        step = self.stages[self.clamp_stage(stage)]
        return (
            max(0, first_note + step.low_offset),
            min(127, first_note + step.high_offset),
        )


# Keyboard (piano) is the only profile confirmed against the running game.
# The unlock order was supplied by the user: the window is always C3-B5, but
# only C3-B4 sounds until the first achievement widens it.
KEYBOARD = InstrumentProfile(
    key="keyboard",
    label="キーボード（ピアノ）",
    initial_state=(0, 0),
    stages=(
        UnlockStage("初期状態（C3-B4）", 0, 23),
        UnlockStage("実績① C5-B6 解放（C3-B6）", 0, 47),
        UnlockStage("実績② A0-B2 解放（A0-B6）", -27, 47),
        UnlockStage("実績③ C7-C8 解放（A0-C8）", -27, 60),
    ),
    selectable=True,
)

# The three profiles below come from CLAUDE.md 10.1. Their ranges were read
# off the game UI, but no unlock order is known and none of them has been
# played through this tool, so they stay unselectable.
GUITAR = InstrumentProfile(
    key="guitar",
    label="ギター",
    initial_state=(0, 0),
    stages=(UnlockStage("E2-D6", -8, 38),),
    selectable=False,
    note="音域の解放順が未検証のため選択できません。",
)

BASS = InstrumentProfile(
    key="bass",
    label="ベース",
    initial_state=(-3, 0),  # Bass opens on the left window, not the middle.
    stages=(UnlockStage("E1-F4", -20, 17),),
    selectable=False,
    note="音域の解放順が未検証のため選択できません。",
)

# Drums are not a transposition problem at all: MIDI channel 10 pitches are
# General MIDI percussion numbers, so they need a lookup table rather than an
# octave shift. See CLAUDE.md 10.2.
DRUMS = InstrumentProfile(
    key="drums",
    label="ドラム",
    initial_state=(0, 0),
    stages=(UnlockStage("C4-B5", 12, 35),),
    selectable=False,
    note="打楽器番号とゲーム24鍵の対応表が未調査のため選択できません。",
)

INSTRUMENTS: tuple[InstrumentProfile, ...] = (KEYBOARD, GUITAR, BASS, DRUMS)
DEFAULT_INSTRUMENT = KEYBOARD.key
# Existing configs predate this setting, so the default keeps the old
# behaviour: the whole A0-C8 keyboard is treated as playable.
DEFAULT_UNLOCK_STAGE = len(KEYBOARD.stages) - 1


def instrument_profile(key: str) -> InstrumentProfile:
    for profile in INSTRUMENTS:
        if profile.key == key:
            return profile
    return KEYBOARD
