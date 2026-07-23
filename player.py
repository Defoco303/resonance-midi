from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import ctypes
import heapq
import threading
import time
from typing import Callable

from instruments import (
    DEFAULT_INSTRUMENT,
    DEFAULT_UNLOCK_STAGE,
    InstrumentProfile,
    drum_note_for_gm,
    instrument_profile,
)
from midi_parser import MidiNote, MidiSong
from range_correction import fold_notes


@dataclass(frozen=True)
class TimedEvent:
    time: float
    pressed: bool
    note: int


KeyboardState = tuple[int, int]  # (three-octave base bank, octave modifier)
INITIAL_KEYBOARD_STATE: KeyboardState = (0, 0)
KEYBOARD_STATES: tuple[KeyboardState, ...] = (
    (-3, 0), (-3, 1),
    (0, -1), (0, 0), (0, 1),
    (3, -1), (3, 0),
)
CONTROL_COST = {"LSHIFT": 100, "LCTRL": 100, ".": 110, ",": 110}


def next_keyboard_state(state: KeyboardState, control: str) -> KeyboardState:
    """Apply one Star Resonance keyboard-range toggle.

    The three-octave base bank and Shift/Ctrl modifier are separate state.
    Shift and Ctrl replace one another, so switching directly between them
    changes the displayed range by two octaves.
    """
    base, modifier = state
    if control == "LSHIFT":
        if base == 3:  # Shift is disabled in the highest base bank.
            return state
        return base, (0 if modifier == 1 else 1)
    if control == "LCTRL":
        if base == -3:  # Ctrl is disabled in the lowest base bank.
            return state
        return base, (0 if modifier == -1 else -1)
    if control == ".":  # Physical JIS > key.
        if base < 3 and base + modifier <= 0:
            return base + 3, modifier
        return state
    if control == ",":  # Physical JIS < key.
        if base > -3 and base + modifier >= 0:
            return base - 3, modifier
        return state
    raise ValueError(f"Unknown keyboard-range control: {control}")


def build_keyboard_paths() -> dict[tuple[KeyboardState, KeyboardState], tuple[str, ...]]:
    """Return the cheapest valid control sequence between all reachable states."""
    paths: dict[tuple[KeyboardState, KeyboardState], tuple[str, ...]] = {}
    controls = ("LSHIFT", "LCTRL", ".", ",")
    for start in KEYBOARD_STATES:
        queue: list[tuple[int, int, KeyboardState, tuple[str, ...]]] = [(0, 0, start, ())]
        best: dict[KeyboardState, int] = {start: 0}
        serial = 0
        while queue:
            cost, _, state, sequence = heapq.heappop(queue)
            if cost != best.get(state):
                continue
            paths[(start, state)] = sequence
            for control in controls:
                target = next_keyboard_state(state, control)
                if target == state or target not in KEYBOARD_STATES:
                    continue
                target_cost = cost + CONTROL_COST[control]
                if target_cost < best.get(target, 10**12):
                    best[target] = target_cost
                    serial += 1
                    heapq.heappush(queue, (target_cost, serial, target, sequence + (control,)))
    return paths


KEYBOARD_PATHS = build_keyboard_paths()


class MidiPlayer:
    def __init__(
        self,
        key_sender: Callable[[str, bool], None],
        position_callback: Callable[[float, str], None],
        error_callback: Callable[[str], None],
    ):
        self._send = key_sender
        self._on_position = position_callback
        self._on_error = error_callback
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._shutdown = False
        self._song: MidiSong | None = None
        self._events: list[TimedEvent] = []
        self._event_times: list[float] = []
        self._index = 0
        self._position = 0.0
        self._state = "stopped"
        self._speed = 1.0
        self._transpose = 0
        self._mapping: dict[int, str] = {}
        self._normal_first_note = 48
        self._profile: InstrumentProfile = instrument_profile(DEFAULT_INSTRUMENT)
        self._unlock_stage = DEFAULT_UNLOCK_STAGE
        self._range_correction = False
        self._natural_decay = self._profile.natural_decay
        self._initial_state: KeyboardState = self._profile.initial_state
        self._supported_first_note = 21
        self._supported_last_note = 108
        self._range_stats = {"folded_notes": 0, "unplayable_notes": 0}
        self._audible_notes: list[MidiNote] = []
        self._state_mappings: dict[KeyboardState, dict[int, str]] = {}
        self._low_mapping: dict[int, str] = {}
        self._high_mapping: dict[int, str] = {}
        self._octave_plan: dict[float, KeyboardState | str] = {}
        self._octave_plan_stats = {"shift_taps": 0, "pulse_batches": 0, "control_taps": 0}
        self._keyboard_state = self._initial_state
        self._auto_octave = False
        self._octave_switch_delay = 0.018
        self._press_ms = 80
        self._ignore_drums = True
        # Identity-based key tracking: one physical key sounds one pitch at a
        # time. These let a held note survive an octave switch and be released
        # on the exact key it was struck on (see _dispatch_locked).
        self._key_pitch: dict[str, int] = {}   # physical key -> pitch sounding
        self._pitch_key: dict[int, str] = {}   # pitch -> key it sounds on
        self._active_since: dict[str, float] = {}
        self._high_resolution_timer = False
        try:
            self._high_resolution_timer = ctypes.windll.winmm.timeBeginPeriod(1) == 0
        except (AttributeError, OSError):
            pass
        self._thread = threading.Thread(target=self._run, name="midi-playback", daemon=True)
        self._thread.start()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def position(self) -> float:
        with self._lock:
            return self._position

    @property
    def octave_plan_stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._octave_plan_stats)

    @property
    def range_stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._range_stats)

    @property
    def audible_notes(self) -> list[MidiNote]:
        """The notes that will actually sound, at the pitch they will sound.

        Drum exclusion, transpose and range correction are already applied and
        anything the current view cannot reach has been dropped, so writing
        this out gives a faithful preview of the performance.
        """
        with self._lock:
            return list(self._audible_notes)

    @property
    def keyboard_shifted(self) -> bool:
        with self._lock:
            # Kept for the UI's existing "refocus before restoring" check.
            return self._keyboard_state != self._initial_state

    def load(self, song: MidiSong) -> None:
        with self._lock:
            self._release_all_locked()
            self._restore_normal_keyboard_locked()
            self._song = song
            self._build_events_locked()
            self._position = 0.0
            self._index = 0
            self._state = "stopped"
        self._wake.set()
        self._on_position(0.0, "stopped")

    def configure(self, mapping: dict[int, str], transpose: int, speed: float, press_ms: int,
                  ignore_drums: bool = True, auto_octave: bool = False,
                  octave_switch_ms: int = 18, instrument: str = DEFAULT_INSTRUMENT,
                  unlock_stage: int = DEFAULT_UNLOCK_STAGE,
                  range_correction: bool = False) -> None:
        with self._lock:
            profile = instrument_profile(instrument)
            stage = profile.clamp_stage(unlock_stage)
            if self._keyboard_state != self._initial_state and not auto_octave:
                self._restore_normal_keyboard_locked()
            rebuild = (press_ms != self._press_ms
                       or ignore_drums != self._ignore_drums
                       # The sounding range and the transpose both decide how
                       # notes are folded, so the event list is no longer valid.
                       or int(transpose) != self._transpose
                       or bool(range_correction) != self._range_correction
                       or profile.key != self._profile.key
                       or stage != self._unlock_stage)
            self._profile = profile
            self._unlock_stage = stage
            self._range_correction = bool(range_correction)
            self._natural_decay = profile.natural_decay
            if profile.initial_state != self._initial_state:
                # Picking up a different instrument in game reopens its own
                # starting window, so the tracked position restarts there too.
                self._keyboard_state = profile.initial_state
            self._initial_state = profile.initial_state
            self._mapping = dict(mapping)
            first_note = min(self._mapping, default=48)
            self._normal_first_note = first_note
            # Only the range unlocked by achievements actually makes a sound,
            # so notes outside it must not move the keyboard either.
            self._supported_first_note, self._supported_last_note = (
                profile.sounding_range(first_note, stage)
            )
            if profile.key == "drums":
                # Drums are voiced by a discrete lookup, not the contiguous
                # sounding_range (whose drum stages are unconfirmed). Cover the
                # nine fixed keys so this unlocked build never filters them out.
                self._supported_first_note = first_note + 14  # closed hi-hat
                self._supported_last_note = first_note + 33   # ride
            self._state_mappings = {
                state: {
                    note + (state[0] + state[1]) * 12: key
                    for note, key in self._mapping.items()
                    if (self._supported_first_note
                        <= note + (state[0] + state[1]) * 12
                        <= self._supported_last_note)
                }
                for state in KEYBOARD_STATES
            }
            self._low_mapping = dict(self._state_mappings.get((-3, 0), {}))
            # After >, the complete physical keyboard addresses C6-B8. The
            # supported-range filter trims it at the game's final C8 key.
            self._high_mapping = dict(self._state_mappings.get((3, 0), {}))
            self._auto_octave = bool(auto_octave)
            self._octave_switch_delay = max(0, min(int(octave_switch_ms), 100)) / 1000
            # Transpose is a pitch shift and drums are not pitched, so it is
            # forced off for the drum kit (see _build_drum_events_locked).
            self._transpose = 0 if profile.key == "drums" else int(transpose)
            self._speed = max(0.1, min(float(speed), 4.0))
            self._press_ms = max(0, int(press_ms))
            self._ignore_drums = bool(ignore_drums)
            if rebuild and self._song:
                old_position = self._position
                self._release_all_locked()
                self._build_events_locked()
                self._position = old_position
                self._index = bisect_left(self._event_times, old_position)
            elif self._song:
                self._build_octave_plan_locked()
        self._wake.set()

    def _will_sound_locked(self, pitch: int) -> bool:
        """Whether a key exists for this pitch in a view the player can reach."""
        if self._auto_octave:
            return any(pitch in mapping for mapping in self._state_mappings.values())
        return pitch in self._mapping

    def _build_drum_events_locked(self, events: list[TimedEvent],
                                  audible: list[MidiNote]) -> None:
        """Turn channel-10 percussion into the game's nine fixed drum keys.

        Drums are a lookup, not a transposition: each GM percussion number is
        remapped onto one of nine notes of the normal C3-B5 window, so the
        existing note->key mapping plays it with no octave switching at all.
        Melodic channels are dropped because the drum kit cannot voice them.
        """
        first = self._normal_first_note
        stage = self._unlock_stage
        for note in self._song.notes:
            if note.channel != 9:
                continue
            # Correction on: redirect not-yet-unlocked sounds to an unlocked one.
            # Correction off: a locked sound is dropped (silent), like a melodic
            # out-of-range note.
            target = drum_note_for_gm(note.note, first, stage, self._range_correction)
            if target is None:
                # No key, or a locked sound with correction off: silently dropped.
                self._range_stats["unplayable_notes"] += 1
                continue
            if self._range_correction and drum_note_for_gm(note.note, first, stage, False) is None:
                # It only sounds because correction redirected a locked sound.
                self._range_stats["folded_notes"] += 1
            audible.append(MidiNote(note.start, note.end, target,
                                    note.velocity, note.channel, note.track))
            # Drums are one-shots: a fixed short strike (never a held key) so a
            # repeated hit on the same key always re-triggers. Key-hold has no
            # musical meaning for percussion, so press_ms is ignored here.
            events.append(TimedEvent(note.start, True, target))
            events.append(TimedEvent(note.start + 0.008, False, target))

    def _build_events_locked(self) -> None:
        events: list[TimedEvent] = []
        audible: list[MidiNote] = []
        self._range_stats = {"folded_notes": 0, "unplayable_notes": 0}
        if self._song and self._profile.key == "drums":
            self._build_drum_events_locked(events, audible)
        elif self._song:
            notes = [
                note for note in self._song.notes
                if not (self._ignore_drums and note.channel == 9)
            ]
            if self._range_correction:
                shifts = fold_notes(notes, self._transpose,
                                    self._supported_first_note,
                                    self._supported_last_note)
            else:
                shifts = [0] * len(notes)
            # Attack times per sounding pitch (= per physical key in a window), so
            # a held note can be released just before the next hit of the same
            # note. Otherwise a legato repeat's release lands in the same game
            # frame as the re-press and the two notes merge into one long note.
            attacks_by_pitch: dict[int, list[float]] = {}
            for note, shift in zip(notes, shifts):
                attacks_by_pitch.setdefault(note.note + shift, []).append(note.start)
            for starts in attacks_by_pitch.values():
                starts.sort()
            for note, shift in zip(notes, shifts):
                pitch = note.note + shift
                if not (self._supported_first_note
                        <= pitch + self._transpose
                        <= self._supported_last_note):
                    # Silent in the game either way; count it so the UI can
                    # say how much of the song will not be heard.
                    self._range_stats["unplayable_notes"] += 1
                if shift:
                    self._range_stats["folded_notes"] += 1
                if self._will_sound_locked(pitch + self._transpose):
                    # Keep the sounding pitch so an export matches what is
                    # heard in game, not what the file originally said.
                    audible.append(MidiNote(note.start, note.end,
                                            pitch + self._transpose, note.velocity,
                                            note.channel, note.track))
                # Strings hold for the whole notated note (like press_ms 0) so
                # the user never has to tune key-hold per instrument; the octave
                # planner is free to release them early to reposition because the
                # sound rings on regardless.
                if self._press_ms == 0 or self._natural_decay:
                    end = note.end
                else:
                    end = min(note.end, note.start + self._press_ms / 1000)
                # Leave a gap before the next hit of the same note so the game
                # sees the release and re-triggers instead of merging them.
                starts = attacks_by_pitch[pitch]
                index = bisect_right(starts, note.start)
                if index < len(starts):
                    end = min(end, starts[index] - 0.03)
                end = max(end, note.start + 0.008)
                events.append(TimedEvent(note.start, True, pitch))
                events.append(TimedEvent(end, False, pitch))
        # Releases come first when a re-trigger occurs at precisely the same time.
        events.sort(key=lambda item: (item.time, item.pressed, item.note))
        self._audible_notes = audible
        self._events = events
        self._event_times = [item.time for item in events]
        self._build_octave_plan_locked()

    def _build_octave_plan_locked(self) -> None:
        """Precompute the cheapest normal/Shift/> route for every attack batch.

        Every reachable base/modifier combination is considered. Dynamic
        programming minimizes valid Shift/Ctrl/>/< transitions for the whole
        song, including the final return to C3-B5. A C3 plus C6 attack cannot
        fit in one three-octave view and retains the fast > pulse.
        """
        self._octave_plan = {}
        self._octave_plan_stats = {"shift_taps": 0, "pulse_batches": 0, "control_taps": 0}
        if not self._auto_octave or not self._events:
            return

        batches: list[tuple[float, tuple[int, ...], int]] = []
        index = 0
        while index < len(self._events):
            batch_time = self._events[index].time
            batch: list[TimedEvent] = []
            while index < len(self._events) and abs(self._events[index].time - batch_time) < 0.0005:
                batch.append(self._events[index])
                index += 1
            # Ignore notes outside the physical A0-C8 keyboard so they do not
            # cause unnecessary range movement.
            pitches = tuple(
                event.note + self._transpose for event in batch
                if event.pressed and
                self._supported_first_note <= event.note + self._transpose <= self._supported_last_note
            )
            if not pitches:
                continue
            compatible = any(all(pitch in mapping for pitch in pitches)
                             for mapping in self._state_mappings.values())
            split_supported = all(
                pitch in self._low_mapping
                or pitch in self._mapping
                or pitch in self._high_mapping
                for pitch in pitches
            )
            pulse_moves = 0
            if not compatible and split_supported:
                if any(pitch in self._low_mapping for pitch in pitches):
                    pulse_moves += 2  # < then >
                if any(pitch in self._high_mapping for pitch in pitches):
                    pulse_moves += 2  # > then <
            batches.append((batch_time, pitches, pulse_moves))

        def path_cost(start: KeyboardState, end: KeyboardState) -> int:
            return sum(CONTROL_COST[key] for key in KEYBOARD_PATHS[(start, end)])

        scores: dict[KeyboardState, int] = {
            state: (0 if state == self._initial_state else 10**12)
            for state in KEYBOARD_STATES
        }
        history: list[dict[KeyboardState, tuple[KeyboardState, KeyboardState | str]]] = []

        for _, pitches, pulse_moves in batches:
            next_scores = {state: 10**12 for state in KEYBOARD_STATES}
            choices: dict[KeyboardState, tuple[KeyboardState, KeyboardState | str]] = {}

            def offer(end_state: KeyboardState, previous: KeyboardState,
                      extra_cost: int, action: KeyboardState | str) -> None:
                candidate = scores[previous] + extra_cost
                if candidate < next_scores[end_state]:
                    next_scores[end_state] = candidate
                    choices[end_state] = (previous, action)

            for previous in KEYBOARD_STATES:
                if scores[previous] >= 10**12:
                    continue
                for target, mapping in self._state_mappings.items():
                    if all(pitch in mapping for pitch in pitches):
                        offer(target, previous, path_cost(previous, target), target)
                if pulse_moves:
                    # Return to C3-B5 and briefly visit the required outer
                    # banks, always ending back at the initial view.
                    pulse_cost = path_cost(previous, self._initial_state) + 120 * pulse_moves
                    offer(self._initial_state, previous, pulse_cost, "pulse")
            scores = next_scores
            history.append(choices)

        end_state = min(KEYBOARD_STATES,
                        key=lambda state: scores[state] + path_cost(state, self._initial_state))
        actions: list[KeyboardState | str] = [self._initial_state] * len(batches)
        state = end_state
        for position in range(len(batches) - 1, -1, -1):
            previous, mode = history[position][state]
            actions[position] = mode
            state = previous

        simulated_state = self._initial_state
        shift_taps = 0
        pulse_batches = 0
        control_taps = 0
        for (batch_time, _, pulse_moves), action in zip(batches, actions):
            target = self._initial_state if action == "pulse" else action
            sequence = KEYBOARD_PATHS[(simulated_state, target)]
            shift_taps += sum(key == "LSHIFT" for key in sequence)
            control_taps += len(sequence)
            simulated_state = target
            if action == "pulse":
                pulse_batches += 1
                control_taps += pulse_moves
            self._octave_plan[batch_time] = action
        final_sequence = KEYBOARD_PATHS[(simulated_state, self._initial_state)]
        shift_taps += sum(key == "LSHIFT" for key in final_sequence)
        control_taps += len(final_sequence)
        self._octave_plan_stats = {
            "shift_taps": shift_taps,
            "pulse_batches": pulse_batches,
            "control_taps": control_taps,
        }

    def play(self) -> bool:
        with self._lock:
            if not self._song:
                return False
            if self._position >= self._song.duration:
                self._position = 0.0
                self._index = 0
            self._state = "playing"
        self._wake.set()
        return True

    def prepare_for_playback(self) -> None:
        """Set the next attack's planned view while the UI countdown runs."""
        with self._lock:
            if not self._auto_octave or not self._song:
                return
            index = self._index
            while index < len(self._events):
                attack_time = self._events[index].time
                batch: list[TimedEvent] = []
                while index < len(self._events) and abs(self._events[index].time - attack_time) < 0.0005:
                    batch.append(self._events[index])
                    index += 1
                if not any(event.pressed for event in batch):
                    continue
                action = self._octave_plan.get(attack_time)
                if action is None:
                    return
                target = self._initial_state if action == "pulse" else action
                self._set_keyboard_state_locked(target)
                return

    def pause(self) -> None:
        with self._lock:
            if self._state == "playing":
                self._state = "paused"
                self._release_all_locked()
                self._restore_normal_keyboard_locked()
        self._wake.set()

    def toggle(self) -> bool:
        if self.state == "playing":
            self.pause()
            return False
        return self.play()

    def stop(self) -> None:
        with self._lock:
            self._state = "stopped"
            self._release_all_locked()
            self._restore_normal_keyboard_locked()
            position = self._position
        self._wake.set()
        self._on_position(position, "stopped")

    def seek(self, position: float) -> None:
        with self._lock:
            duration = self._song.duration if self._song else 0.0
            self._position = max(0.0, min(float(position), duration))
            self._release_all_locked()
            self._restore_normal_keyboard_locked()
            self._index = bisect_left(self._event_times, self._position)
        self._wake.set()
        self._on_position(self._position, self._state)

    def restart(self, play: bool = True) -> None:
        self.seek(0.0)
        if play:
            self.play()

    def close(self) -> None:
        with self._lock:
            self._shutdown = True
            self._release_all_locked()
            self._restore_normal_keyboard_locked()
        self._wake.set()
        self._thread.join(timeout=1.0)
        if self._high_resolution_timer:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except (AttributeError, OSError):
                pass
            self._high_resolution_timer = False

    def _release_all_locked(self) -> None:
        for key in list(self._key_pitch):
            try:
                self._send(key, False)
            except Exception:
                pass
        self._key_pitch.clear()
        self._pitch_key.clear()
        self._active_since.clear()

    def _dispatch_locked(self, event: TimedEvent, mapping: dict[int, str] | None = None) -> None:
        pitch = event.note + self._transpose
        try:
            if event.pressed:
                key = (mapping or self._mapping).get(pitch)
                if not key:
                    return
                # A physical key sounds one pitch. Free the key of whatever it is
                # holding, and free this pitch from any other key, then strike.
                occupant = self._key_pitch.get(key)
                if occupant is not None:
                    self._send(key, False)
                    self._pitch_key.pop(occupant, None)
                previous = self._pitch_key.get(pitch)
                if previous is not None and previous != key:
                    self._send(previous, False)
                    self._key_pitch.pop(previous, None)
                    self._active_since.pop(previous, None)
                self._send(key, True)
                self._key_pitch[key] = pitch
                self._pitch_key[pitch] = key
                self._active_since[key] = time.perf_counter()
            else:
                # Release the key the note was actually struck on, which can
                # differ from the current window's mapping after a switch.
                key = self._pitch_key.get(pitch)
                if key is None:
                    return
                # Guarantee a real, observable hold instead of releasing an
                # overdue note (whose time a range change consumed) immediately.
                elapsed = time.perf_counter() - self._active_since.get(key, 0.0)
                if elapsed < 0.008:
                    time.sleep(0.008 - elapsed)
                self._send(key, False)
                self._key_pitch.pop(key, None)
                self._pitch_key.pop(pitch, None)
                self._active_since.pop(key, None)
        except Exception as exc:
            self._state = "paused"
            self._release_all_locked()
            self._restore_normal_keyboard_locked()
            self._on_error(f"キー送信に失敗しました: {exc}")

    def _tap_control_locked(self, key: str, hold_seconds: float = 0.0) -> None:
        self._send(key, True)
        if hold_seconds > 0:
            time.sleep(hold_seconds)
        self._send(key, False)

    def _set_keyboard_state_locked(self, target: KeyboardState) -> None:
        if self._keyboard_state == target:
            return
        # Hold-through-switch: held notes are NOT released here. The game keeps a
        # held key sounding while the window moves (verified on the real game),
        # so the note rings on across the switch even with sustain off. Identity
        # tracking (_pitch_key) still releases each note on its original key, and
        # a new note that needs a currently-held key frees it in _dispatch_locked.
        for control in KEYBOARD_PATHS[(self._keyboard_state, target)]:
            # Modifier toggles are frame-polled by the game. A longer press is
            # safe when issued during the rest before the target note.
            hold = (max(0.020, min(0.050, self._octave_switch_delay + 0.010))
                    if control in ("LSHIFT", "LCTRL") else 0.0)
            self._tap_control_locked(control, hold)
            self._keyboard_state = next_keyboard_state(self._keyboard_state, control)
            if self._octave_switch_delay:
                time.sleep(self._octave_switch_delay)

    def _restore_normal_keyboard_locked(self) -> None:
        if self._keyboard_state != self._initial_state:
            self._set_keyboard_state_locked(self._initial_state)

    def _prepare_next_keyboard_state_locked(self) -> None:
        """Use the rest before the next attack to finish its range change.

        Normally a held key blocks this (moving the keyboard releases every held
        key, which would cut a piano note). A natural-decay instrument keeps
        ringing after release, so it may reposition mid-note: the held keys are
        freed and the sound sustains on its own.
        """
        if not self._auto_octave:
            return
        if self._key_pitch and not self._natural_decay:
            return
        index = self._index
        while index < len(self._events):
            attack_time = self._events[index].time
            batch: list[TimedEvent] = []
            while index < len(self._events) and abs(self._events[index].time - attack_time) < 0.0005:
                batch.append(self._events[index])
                index += 1
            if not any(event.pressed for event in batch):
                continue
            action = self._octave_plan.get(attack_time)
            if action is None:
                return
            target = self._initial_state if action == "pulse" else action
            if target == self._keyboard_state:
                return
            sequence = KEYBOARD_PATHS[(self._keyboard_state, target)]
            modifier_hold = max(0.020, min(0.050, self._octave_switch_delay + 0.010))
            transition_seconds = sum(
                (modifier_hold if key in ("LSHIFT", "LCTRL") else 0.0)
                + self._octave_switch_delay
                for key in sequence
            )
            # Begin only shortly before it is needed; this also leaves earlier
            # notes and their releases in the old keyboard view.
            time_until_attack = (attack_time - self._position) / self._speed
            if 0 < time_until_attack <= transition_seconds + 0.015:
                self._set_keyboard_state_locked(target)
            return

    def _dispatch_batch_locked(self, events: list[TimedEvent]) -> None:
        """Dispatch one timestamp, visiting the outer banks for a pulse.

        A pulse batch spans more than one 3-octave window. Each note is struck in
        its bank and left held (hold-through): it keeps ringing across the return
        move and is released on its own key at its note-off (identity tracking).
        """
        if not self._auto_octave:
            for event in events:
                self._dispatch_locked(event)
            return

        action = self._octave_plan.get(events[0].time, self._keyboard_state)
        if action != "pulse":
            target = action
            self._set_keyboard_state_locked(target)
            mapping = self._state_mappings.get(target, self._mapping)
            for event in events:
                self._dispatch_locked(event, mapping)
            return

        low_attacks = [
            event for event in events
            if event.pressed and event.note + self._transpose in self._low_mapping
        ]
        high_attacks = [
            event for event in events
            if event.pressed and event.note + self._transpose in self._high_mapping
        ]
        # Releases first: identity tracking frees each note on its original key,
        # so the current window does not matter here.
        for event in events:
            if not event.pressed:
                self._dispatch_locked(event)
        # Middle-bank note-ons play in the initial window and stay held.
        self._set_keyboard_state_locked(self._initial_state)
        for event in events:
            pitch = event.note + self._transpose
            if (event.pressed and pitch not in self._low_mapping
                    and pitch not in self._high_mapping):
                self._dispatch_locked(event)
        if not low_attacks and not high_attacks:
            return

        try:
            for attacks, mapping, target in (
                (low_attacks, self._low_mapping, (-3, 0)),
                (high_attacks, self._high_mapping, (3, 0)),
            ):
                if not attacks:
                    continue
                self._set_keyboard_state_locked(target)
                for event in attacks:
                    self._dispatch_locked(event, mapping)
                # Let the strike register before moving the window away; the held
                # key keeps sounding through the return move.
                time.sleep(max(0.008, min(0.020, self._octave_switch_delay)))
                self._set_keyboard_state_locked(self._initial_state)
        except Exception as exc:
            self._state = "paused"
            self._release_all_locked()
            self._restore_normal_keyboard_locked()
            self._on_error(f"4オクターブ自動切替に失敗しました: {exc}")

    def _run(self) -> None:
        try:
            # HIGHEST is below TIME_CRITICAL: key timing wins over GUI paints
            # without risking starvation of essential Windows threads.
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentThread.restype = ctypes.c_void_p
            kernel32.SetThreadPriority.argtypes = (ctypes.c_void_p, ctypes.c_int)
            kernel32.SetThreadPriority.restype = ctypes.c_int
            kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 2)
        except (AttributeError, OSError):
            pass
        last_real = time.perf_counter()
        last_report = 0.0
        while True:
            with self._lock:
                if self._shutdown:
                    return
                playing = self._state == "playing" and self._song is not None
            if not playing:
                self._wake.wait(0.1)
                self._wake.clear()
                last_real = time.perf_counter()
                continue

            now = time.perf_counter()
            real_delta = min(now - last_real, 0.1)
            last_real = now
            report = None
            with self._lock:
                if self._state != "playing" or not self._song:
                    continue
                self._position = min(self._song.duration, self._position + real_delta * self._speed)
                self._prepare_next_keyboard_state_locked()
                while self._index < len(self._events) and self._events[self._index].time <= self._position + 0.001:
                    event_time = self._events[self._index].time
                    batch: list[TimedEvent] = []
                    while (self._index < len(self._events)
                           and abs(self._events[self._index].time - event_time) < 0.0005):
                        batch.append(self._events[self._index])
                        self._index += 1
                    self._dispatch_batch_locked(batch)
                if self._position >= self._song.duration:
                    self._release_all_locked()
                    self._restore_normal_keyboard_locked()
                    self._state = "stopped"
                    self._position = 0.0
                    self._index = 0
                    report = (0.0, "ended")
                elif now - last_report >= 0.05:
                    report = (self._position, "playing")
                    last_report = now
            if report:
                self._on_position(*report)
            self._wake.wait(0.002)
            self._wake.clear()
