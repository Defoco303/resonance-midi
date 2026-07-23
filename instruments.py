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
    # Strings ring on after the key is released, so the octave planner may free
    # held keys to reposition mid-note without cutting the sound (see player).
    natural_decay: bool = False

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
    # Trial (2026-07-23): treat piano as natural-decay too. It relies on the
    # game sustain pedal being ON to carry a note after the key is freed for a
    # switch; with sustain OFF this can clip notes at switch points.
    natural_decay=True,
)

# The three profiles below have their ranges and unlock order from the user
# (2026-07-26), but stay unselectable: the switch rules were never checked
# against these instruments, and each has non-range unlocks (playing
# techniques) whose input is unknown. Stages are cumulative like the keyboard.
#
# Guitar also unlocks harmonics / overdrive / distortion. These are playing
# techniques, not extra range, and how the game triggers them is unknown, so
# only the pitch range is modelled here.
GUITAR = InstrumentProfile(
    key="guitar",
    label="ギター",
    initial_state=(0, 0),
    stages=(
        UnlockStage("初期状態（C3-B4）", 0, 23),
        UnlockStage("解放①（E2-B4）", -8, 23),
        UnlockStage("解放②（E2-D6）", -8, 38),
    ),
    selectable=True,
    note="切替ルールと奏法（ハーモニクス等）は未確認です（実機未検証・ベータ）。",
    natural_decay=True,
)

# Bass opens on the left window, not the middle. It also unlocks mute /
# harmonics / slap / overdrive as playing techniques, handled the same as
# guitar: range only.
BASS = InstrumentProfile(
    key="bass",
    label="ベース",
    initial_state=(-3, 0),
    stages=(
        UnlockStage("初期状態（E1-B2）", -20, -1),
        UnlockStage("解放①（E1-F4）", -20, 17),
    ),
    selectable=True,
    note="初期位置が左窓（Z=C0、実発音 D=E1〜）。切替ルールや奏法は未確認（実機未検証・ベータ）。",
    natural_decay=True,
)

# Drums are not a transposition problem at all: MIDI channel 10 pitches are
# General MIDI percussion numbers, so they need a lookup table rather than an
# octave shift. See CLAUDE.md 10.2. The stages below are the user's best guess
# (2026-07-26) and unconfirmed; the added ranges also leave gaps, which the
# contiguous range model here cannot represent. Kept only as a placeholder.
#   初期 A4-E5  スネア / トム
#   解放① C4-G4?  バスドラム / ハイハット
#   解放② F5-B5?  クラッシュ / ライド
# Playable via the GM->key table below (DRUM_GM_OFFSETS). The drum stages gate
# which of the nine sounds actually play; a locked sound is redirected to an
# unlocked one (see _DRUM_UNLOCK / _DRUM_FALLBACK, and player._build_drum_events).
# The low/high offsets are vestigial (the drum play path overrides the range).
# Flip ``selectable`` back to False to hide drums again (e.g. before publishing).
DRUMS = InstrumentProfile(
    key="drums",
    label="ドラム",
    initial_state=(0, 0),
    stages=(
        UnlockStage("初期状態（スネアドラム、トムトム）", 21, 28),
        UnlockStage("解放①（バスドラム、ハイハット）", 14, 28),
        UnlockStage("解放②（クラッシュシンバル、ライドシンバル）", 14, 33),
    ),
    selectable=True,
    note="GM打楽器番号を9個の固定ドラムキーへ変換して再生します（実機未検証・ベータ）。",
)

# --- Drum percussion mapping -------------------------------------------------
#
# The game exposes only nine drum sounds, each on a fixed physical key. Those
# keys land on nine (discrete, non-contiguous) notes of the normal C3-B5 window,
# so a General MIDI channel-10 note is played by remapping its percussion number
# onto one of these nine window notes; the existing note->key mapping and the
# "drums never switch" path then handle it unchanged. Offsets are semitones from
# C3 so they follow ``game_octave_offset`` like the rest of this module.
#
# Confirmed keys (user, real game 2026-07-23):
#   S=クローズ/ペダルHH D4(+14)  F=バスドラム F4(+17)  H=フロアタム A4(+21)
#   Q=スネア C5(+24)  W=ミッドタム D5(+26)  E=ハイタム E5(+28)
#   R=クラッシュ F5(+29)  T=オープンHH G5(+31)  Y=ライド A5(+33)
_DRUM = {
    "closed_hh": 14, "bass": 17, "floor_tom": 21, "snare": 24, "mid_tom": 26,
    "high_tom": 28, "crash": 29, "open_hh": 31, "ride": 33,
}

# General MIDI percussion number (35-81) -> C3 offset of the game drum it plays.
# The GM sounds collapse onto 9 keys (irreversible reduction). Decisions the user
# signed off: Hi-Mid Tom 48 = the high tom; Tambourine 54 -> open hi-hat and
# Cowbell 56 -> ride rather than dropped. The 60-81 hand/Latin percussion block
# is approximated by timbre (2026-07-23): hand drums (bongo/conga/timbale/wood
# block) -> toms by pitch, metallic (agogo/triangle) -> ride, shakers/short
# scrapes (cabasa/maracas/short guiro) -> closed hi-hat, long guiro -> open
# hi-hat, claves -> snare. Left dropped on purpose because no drum-kit voice is
# close enough: 58 Vibraslap, 71/72 Whistles, 78/79 Cuica. Any GM number absent
# from this table (and anything outside 35-81) is silently dropped.
DRUM_GM_OFFSETS: dict[int, int] = {
    35: _DRUM["bass"],       # Acoustic Bass Drum
    36: _DRUM["bass"],       # Bass Drum 1
    37: _DRUM["snare"],      # Side Stick
    38: _DRUM["snare"],      # Acoustic Snare
    39: _DRUM["snare"],      # Hand Clap
    40: _DRUM["snare"],      # Electric Snare
    41: _DRUM["floor_tom"],  # Low Floor Tom
    42: _DRUM["closed_hh"],  # Closed Hi-Hat
    43: _DRUM["floor_tom"],  # High Floor Tom
    44: _DRUM["closed_hh"],  # Pedal Hi-Hat
    45: _DRUM["mid_tom"],    # Low Tom
    46: _DRUM["open_hh"],    # Open Hi-Hat
    47: _DRUM["mid_tom"],    # Low-Mid Tom
    48: _DRUM["high_tom"],   # Hi-Mid Tom -> high tom (user decision)
    49: _DRUM["crash"],      # Crash Cymbal 1
    50: _DRUM["high_tom"],   # High Tom
    51: _DRUM["ride"],       # Ride Cymbal 1
    52: _DRUM["crash"],      # Chinese Cymbal
    53: _DRUM["ride"],       # Ride Bell
    54: _DRUM["open_hh"],    # Tambourine -> open hi-hat (redirected)
    55: _DRUM["crash"],      # Splash Cymbal
    56: _DRUM["ride"],       # Cowbell -> ride (redirected)
    57: _DRUM["crash"],      # Crash Cymbal 2
    59: _DRUM["ride"],       # Ride Cymbal 2
    # --- hand / Latin percussion, approximated by timbre ---
    60: _DRUM["high_tom"],   # High Bongo
    61: _DRUM["mid_tom"],    # Low Bongo
    62: _DRUM["high_tom"],   # Mute High Conga
    63: _DRUM["high_tom"],   # Open High Conga
    64: _DRUM["mid_tom"],    # Low Conga
    65: _DRUM["high_tom"],   # High Timbale
    66: _DRUM["mid_tom"],    # Low Timbale
    67: _DRUM["ride"],       # High Agogo
    68: _DRUM["ride"],       # Low Agogo
    69: _DRUM["closed_hh"],  # Cabasa
    70: _DRUM["closed_hh"],  # Maracas
    73: _DRUM["closed_hh"],  # Short Guiro
    74: _DRUM["open_hh"],    # Long Guiro
    75: _DRUM["snare"],      # Claves
    76: _DRUM["high_tom"],   # Hi Wood Block
    77: _DRUM["mid_tom"],    # Low Wood Block
    80: _DRUM["ride"],       # Mute Triangle
    81: _DRUM["ride"],       # Open Triangle
}

_SOUND_BY_OFFSET = {offset: name for name, offset in _DRUM.items()}

# Which achievement stage unlocks each drum sound (user-corrected 2026-07-23):
#   0 初期    = スネア + 3タム
#   1 解放①  = + バスドラム, クローズ/ペダルHH
#   2 解放②  = + オープンHH, クラッシュ, ライド
_DRUM_UNLOCK = {
    "snare": 0, "high_tom": 0, "mid_tom": 0, "floor_tom": 0,
    "bass": 1, "closed_hh": 1,
    "open_hh": 2, "crash": 2, "ride": 2,
}

# When a sound is still locked, redirect to the first already-unlocked sound in
# its chain. Every chain ends at a stage-0 sound, so a target always exists.
#   初期(0): bass->floor_tom, closed/open_hh & ride->high_tom, crash->snare
#   解放①(1): open_hh & ride->closed_hh, crash->snare
_DRUM_FALLBACK = {
    "bass": ("floor_tom", "mid_tom"),
    "closed_hh": ("open_hh", "ride", "high_tom"),
    "open_hh": ("closed_hh", "ride", "crash", "high_tom"),
    "crash": ("ride", "open_hh", "snare"),
    "ride": ("closed_hh", "crash", "high_tom"),
}


def _available_drum(sound: str, stage: int) -> str | None:
    if _DRUM_UNLOCK.get(sound, 0) <= stage:
        return sound
    for alternative in _DRUM_FALLBACK.get(sound, ()):
        if _DRUM_UNLOCK.get(alternative, 0) <= stage:
            return alternative
    return None


def drum_note_for_gm(gm_note: int, first_note: int = NORMAL_FIRST_NOTE,
                     stage: int = 2, redirect: bool = True) -> int | None:
    """Window note a GM percussion number plays, or None if it will not sound.

    ``first_note`` is the current C3 position (mapping-min, already shifted by
    ``game_octave_offset``); the return value lands in that same keyspace.
    ``stage`` is the drum unlock stage. ``redirect`` mirrors the correction
    toggle: when True a sound the stage has not unlocked is redirected to an
    unlocked one (see _DRUM_FALLBACK); when False it is dropped instead (silent),
    the same way a melodic out-of-range note is dropped without correction.
    Stage 2 (default) is fully unlocked, so redirect makes no difference there.
    """
    offset = DRUM_GM_OFFSETS.get(int(gm_note))
    if offset is None:
        return None
    sound = _SOUND_BY_OFFSET[offset]
    if redirect:
        sound = _available_drum(sound, int(stage))
    elif _DRUM_UNLOCK.get(sound, 0) > int(stage):
        return None  # locked, and not redirecting -> silent
    return None if sound is None else first_note + _DRUM[sound]


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
