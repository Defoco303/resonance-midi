"""Small, dependency-free Standard MIDI File parser.

Only the data needed by the player is retained: note spans, tempo and track names.
Format 0/1 files, running status and both PPQ/SMPTE time divisions are supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct


class MidiError(ValueError):
    pass


@dataclass(frozen=True)
class MidiNote:
    start: float
    end: float
    note: int
    velocity: int
    channel: int
    track: int


@dataclass(frozen=True)
class MidiSong:
    path: Path
    name: str
    duration: float
    notes: tuple[MidiNote, ...]
    track_names: tuple[str, ...]
    initial_bpm: float

    @property
    def note_range(self) -> tuple[int, int] | None:
        if not self.notes:
            return None
        values = [item.note for item in self.notes]
        return min(values), max(values)


def _vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if pos >= len(data):
            raise MidiError("可変長数値の途中でファイルが終了しました")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise MidiError("不正な可変長数値です")


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "cp932", "latin1"):
        try:
            return raw.decode(encoding).strip("\x00 ")
        except UnicodeDecodeError:
            pass
    return ""


def _parse_track(data: bytes, track_index: int):
    pos = 0
    tick = 0
    running_status: int | None = None
    events: list[tuple] = []
    tempos: list[tuple[int, int, int]] = []
    name = f"トラック {track_index + 1}"
    order = 0

    while pos < len(data):
        delta, pos = _vlq(data, pos)
        tick += delta
        if pos >= len(data):
            break

        first = data[pos]
        if first & 0x80:
            status = first
            pos += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise MidiError(f"トラック {track_index + 1}: ランニングステータスが不正です")

        if status == 0xFF:
            running_status = None
            if pos >= len(data):
                raise MidiError("メタイベントが壊れています")
            meta_type = data[pos]
            pos += 1
            length, pos = _vlq(data, pos)
            payload = data[pos : pos + length]
            if len(payload) != length:
                raise MidiError("メタイベントの途中でファイルが終了しました")
            pos += length
            if meta_type == 0x03 and payload:
                name = _decode_text(payload) or name
            elif meta_type == 0x51 and length == 3:
                tempos.append((tick, int.from_bytes(payload, "big"), order))
            elif meta_type == 0x2F:
                break
            order += 1
            continue

        if status in (0xF0, 0xF7):
            running_status = None
            length, pos = _vlq(data, pos)
            pos += length
            if pos > len(data):
                raise MidiError("SysExイベントの途中でファイルが終了しました")
            continue

        kind = status & 0xF0
        channel = status & 0x0F
        length = 1 if kind in (0xC0, 0xD0) else 2
        payload = data[pos : pos + length]
        if len(payload) != length:
            raise MidiError("MIDIイベントの途中でファイルが終了しました")
        if any(byte & 0x80 for byte in payload):
            raise MidiError("MIDIデータバイトが不正です")
        pos += length
        if kind == 0x90:
            note, velocity = payload
            events.append((tick, order, "off" if velocity == 0 else "on", note, velocity, channel))
        elif kind == 0x80:
            note, velocity = payload
            events.append((tick, order, "off", note, velocity, channel))
        order += 1

    return events, tempos, name, tick


def load_midi(path: str | Path) -> MidiSong:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise MidiError(f"MIDIファイルを読み込めません: {exc}") from exc

    if len(raw) < 14 or raw[:4] != b"MThd":
        raise MidiError("Standard MIDI Fileではありません")
    header_len = struct.unpack_from(">I", raw, 4)[0]
    if header_len < 6 or len(raw) < 8 + header_len:
        raise MidiError("MIDIヘッダーが壊れています")
    fmt, track_count, division = struct.unpack_from(">HHH", raw, 8)
    if fmt not in (0, 1):
        raise MidiError(f"MIDIフォーマット {fmt} には未対応です（0/1のみ対応）")

    pos = 8 + header_len
    all_events: list[tuple] = []
    all_tempos: list[tuple[int, int, int, int]] = []
    track_names: list[str] = []
    max_tick = 0
    for track_index in range(track_count):
        if pos + 8 > len(raw) or raw[pos : pos + 4] != b"MTrk":
            raise MidiError(f"トラック {track_index + 1} が見つかりません")
        length = struct.unpack_from(">I", raw, pos + 4)[0]
        pos += 8
        chunk = raw[pos : pos + length]
        if len(chunk) != length:
            raise MidiError(f"トラック {track_index + 1} の途中でファイルが終了しました")
        pos += length
        events, tempos, name, end_tick = _parse_track(chunk, track_index)
        all_events.extend((*event, track_index) for event in events)
        all_tempos.extend((tick, tempo, track_index, order) for tick, tempo, order in tempos)
        track_names.append(name)
        max_tick = max(max_tick, end_tick)

    if division & 0x8000:
        fps_raw = (division >> 8) & 0xFF
        fps_signed = fps_raw - 256
        fps = 29.97 if fps_signed == -29 else float(-fps_signed)
        ticks_per_frame = division & 0xFF
        if fps <= 0 or ticks_per_frame == 0:
            raise MidiError("不正なSMPTEタイムディビジョンです")
        tick_to_seconds = lambda value: value / (fps * ticks_per_frame)
        initial_bpm = 120.0
    else:
        ppq = division
        if ppq == 0:
            raise MidiError("PPQが0です")
        # At identical ticks the last tempo in MIDI order wins.
        tempo_by_tick: dict[int, int] = {0: 500_000}
        for tick, tempo, track, order in sorted(all_tempos, key=lambda item: (item[0], item[2], item[3])):
            if tempo:
                tempo_by_tick[tick] = tempo
        tempo_points = sorted(tempo_by_tick.items())
        segments: list[tuple[int, float, int]] = []
        elapsed = 0.0
        last_tick, current_tempo = tempo_points[0]
        segments.append((last_tick, elapsed, current_tempo))
        for next_tick, next_tempo in tempo_points[1:]:
            elapsed += (next_tick - last_tick) * current_tempo / (ppq * 1_000_000)
            last_tick, current_tempo = next_tick, next_tempo
            segments.append((last_tick, elapsed, current_tempo))

        import bisect
        segment_ticks = [item[0] for item in segments]

        def tick_to_seconds(value: int) -> float:
            index = bisect.bisect_right(segment_ticks, value) - 1
            start_tick, start_seconds, tempo = segments[max(index, 0)]
            return start_seconds + (value - start_tick) * tempo / (ppq * 1_000_000)

        initial_bpm = 60_000_000 / tempo_by_tick.get(0, 500_000)

    active: dict[tuple[int, int, int], list[tuple[int, int]]] = {}
    spans: list[MidiNote] = []
    for tick, order, kind, note, velocity, channel, track in sorted(
        all_events, key=lambda item: (item[0], item[6], item[1])
    ):
        key = (track, channel, note)
        if kind == "on":
            active.setdefault(key, []).append((tick, velocity))
        else:
            queue = active.get(key)
            if queue:
                start_tick, start_velocity = queue.pop(0)
                spans.append(MidiNote(
                    tick_to_seconds(start_tick),
                    max(tick_to_seconds(tick), tick_to_seconds(start_tick) + 0.001),
                    note, start_velocity, channel, track,
                ))

    for (track, channel, note), queue in active.items():
        for start_tick, velocity in queue:
            spans.append(MidiNote(
                tick_to_seconds(start_tick), tick_to_seconds(max(max_tick, start_tick + 1)),
                note, velocity, channel, track,
            ))

    spans.sort(key=lambda item: (item.start, item.note, item.track))
    duration = max((item.end for item in spans), default=tick_to_seconds(max_tick))
    display_name = next((name for name in track_names if name and not name.startswith("トラック ")), source.stem)
    return MidiSong(source, display_name, duration, tuple(spans), tuple(track_names), initial_bpm)


NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(note: int) -> str:
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"
