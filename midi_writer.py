"""Write a standard MIDI file back out, for auditioning what will be played.

This is the counterpart to ``midi_parser`` and shares its no-dependency rule.
It only has to round-trip what the player actually sends, so it writes a
format 1 file at a fixed tempo: note onsets are already absolute seconds by
this point, so the original tempo map is not needed to reproduce the timing.
A DAW will show a different notated tempo, but it will sound the same.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable

from midi_parser import MidiNote


PPQ = 480
MICROSECONDS_PER_BEAT = 500000  # 120 BPM
TICKS_PER_SECOND = PPQ * 1_000_000 / MICROSECONDS_PER_BEAT


def _variable_length(value: int) -> bytes:
    value = max(0, int(value))
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(out)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def _track_chunk(events: list[tuple[int, int, bytes]]) -> bytes:
    # Sort by tick, then note-off before note-on so a repeated pitch retriggers
    # instead of cancelling itself.
    events.sort(key=lambda item: (item[0], item[1]))
    payload = bytearray()
    previous = 0
    for tick, _, data in events:
        payload += _variable_length(tick - previous) + data
        previous = tick
    payload += _variable_length(0) + b"\xff\x2f\x00"
    return _chunk(b"MTrk", bytes(payload))


def write_midi(path: Path | str, notes: Iterable[MidiNote]) -> int:
    """Write ``notes`` to ``path``. Returns the number of notes written."""
    tracks: dict[int, list[tuple[int, int, bytes]]] = {}
    written = 0
    for note in notes:
        pitch = max(0, min(127, note.note))
        status = 0x90 | (note.channel & 0x0F)
        velocity = max(1, min(127, note.velocity))
        events = tracks.setdefault(note.track, [])
        events.append((round(note.start * TICKS_PER_SECOND), 1,
                       bytes((status, pitch, velocity))))
        events.append((round(note.end * TICKS_PER_SECOND), 0,
                       bytes((status, pitch, 0))))
        written += 1
    if not tracks:
        tracks[0] = []
    tempo = _track_chunk([(0, 0, b"\xff\x51\x03"
                          + MICROSECONDS_PER_BEAT.to_bytes(3, "big"))])
    body = b"".join(_track_chunk(events) for _, events in sorted(tracks.items()))
    header = _chunk(b"MThd", struct.pack(">HHH", 1, len(tracks) + 1, PPQ))
    Path(path).write_bytes(header + tempo + body)
    return written
