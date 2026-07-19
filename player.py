from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left
import ctypes
import threading
import time
from typing import Callable

from midi_parser import MidiSong


@dataclass(frozen=True)
class TimedEvent:
    time: float
    pressed: bool
    note: int


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
        self._high_mapping: dict[int, str] = {}
        self._auto_octave = False
        self._octave_switch_delay = 0.018
        self._press_ms = 80
        self._ignore_drums = True
        self._active: dict[str, int] = {}
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

    def load(self, song: MidiSong) -> None:
        with self._lock:
            self._release_all_locked()
            self._song = song
            self._build_events_locked()
            self._position = 0.0
            self._index = 0
            self._state = "stopped"
        self._wake.set()
        self._on_position(0.0, "stopped")

    def configure(self, mapping: dict[int, str], transpose: int, speed: float, press_ms: int,
                  ignore_drums: bool = True, auto_octave: bool = False,
                  octave_switch_ms: int = 18) -> None:
        with self._lock:
            rebuild = press_ms != self._press_ms or ignore_drums != self._ignore_drums
            self._mapping = dict(mapping)
            first_note = min(self._mapping, default=48)
            # After the game's > command, Z-M address the octave three steps
            # above the normal Z-M octave: C6-B6 when normal Z is C3.
            self._high_mapping = {
                note + 36: key for note, key in self._mapping.items()
                if first_note <= note < first_note + 12
            }
            self._auto_octave = bool(auto_octave)
            self._octave_switch_delay = max(0, min(int(octave_switch_ms), 100)) / 1000
            self._transpose = int(transpose)
            self._speed = max(0.1, min(float(speed), 4.0))
            self._press_ms = max(0, int(press_ms))
            self._ignore_drums = bool(ignore_drums)
            if rebuild and self._song:
                old_position = self._position
                self._release_all_locked()
                self._build_events_locked()
                self._position = old_position
                self._index = bisect_left(self._event_times, old_position)
        self._wake.set()

    def _build_events_locked(self) -> None:
        events: list[TimedEvent] = []
        if self._song:
            for note in self._song.notes:
                if self._ignore_drums and note.channel == 9:
                    continue
                end = note.end if self._press_ms == 0 else min(note.end, note.start + self._press_ms / 1000)
                end = max(end, note.start + 0.008)
                events.append(TimedEvent(note.start, True, note.note))
                events.append(TimedEvent(end, False, note.note))
        # Releases come first when a re-trigger occurs at precisely the same time.
        events.sort(key=lambda item: (item.time, item.pressed, item.note))
        self._events = events
        self._event_times = [item.time for item in events]

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

    def pause(self) -> None:
        with self._lock:
            if self._state == "playing":
                self._state = "paused"
                self._release_all_locked()
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
            position = self._position
        self._wake.set()
        self._on_position(position, "stopped")

    def seek(self, position: float) -> None:
        with self._lock:
            duration = self._song.duration if self._song else 0.0
            self._position = max(0.0, min(float(position), duration))
            self._release_all_locked()
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
        self._wake.set()
        self._thread.join(timeout=1.0)
        if self._high_resolution_timer:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except (AttributeError, OSError):
                pass
            self._high_resolution_timer = False

    def _release_all_locked(self) -> None:
        for key in list(self._active):
            try:
                self._send(key, False)
            except Exception:
                pass
        self._active.clear()

    def _dispatch_locked(self, event: TimedEvent) -> None:
        key = self._mapping.get(event.note + self._transpose)
        if not key:
            return
        try:
            count = self._active.get(key, 0)
            if event.pressed:
                if count == 0:
                    self._send(key, True)
                self._active[key] = count + 1
            elif count > 0:
                if count == 1:
                    self._send(key, False)
                    self._active.pop(key, None)
                else:
                    self._active[key] = count - 1
        except Exception as exc:
            self._state = "paused"
            self._release_all_locked()
            self._on_error(f"キー送信に失敗しました: {exc}")

    def _tap_control_locked(self, key: str) -> None:
        self._send(key, True)
        self._send(key, False)

    def _dispatch_batch_locked(self, events: list[TimedEvent]) -> None:
        """Dispatch one timestamp, pulsing C6-B6 through the > keyboard bank.

        Notes in the normal bank are attacked first. They are released before
        the bank changes, but the game's piano decay lets their sound overlap
        the high-bank attack like a very fast arpeggio.
        """
        if not self._auto_octave:
            for event in events:
                self._dispatch_locked(event)
            return

        high_attacks = [
            event for event in events
            if event.pressed and event.note + self._transpose in self._high_mapping
        ]
        for event in events:
            if event.note + self._transpose not in self._high_mapping:
                self._dispatch_locked(event)
        if not high_attacks:
            return

        # Never carry a physical key hold across a keyboard-bank change; its
        # later key-up could otherwise release a different displayed note.
        self._release_all_locked()
        high_keys = list(dict.fromkeys(
            self._high_mapping[event.note + self._transpose] for event in high_attacks
        ))
        pressed: list[str] = []
        try:
            self._tap_control_locked(".")  # Physical JIS > key: C3 -> C6 bank.
            if self._octave_switch_delay:
                time.sleep(self._octave_switch_delay)
            for key in high_keys:
                self._send(key, True)
                pressed.append(key)
            time.sleep(max(0.008, min(0.020, self._octave_switch_delay)))
            for key in reversed(pressed):
                self._send(key, False)
            pressed.clear()
            self._tap_control_locked(",")  # Physical JIS < key: return to C3.
            if self._octave_switch_delay:
                time.sleep(self._octave_switch_delay)
        except Exception as exc:
            for key in reversed(pressed):
                try:
                    self._send(key, False)
                except Exception:
                    pass
            # Best effort return to the normal bank after a partial sequence.
            try:
                self._tap_control_locked(",")
            except Exception:
                pass
            self._state = "paused"
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
                    self._state = "stopped"
                    report = (self._position, "ended")
                elif now - last_report >= 0.05:
                    report = (self._position, "playing")
                    last_report = now
            if report:
                self._on_position(*report)
            self._wake.wait(0.002)
            self._wake.clear()
