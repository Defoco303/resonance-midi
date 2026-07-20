"""Fold out-of-range notes into the sounding range without wrecking the line.

Wrapping each note on its own is what turns a melody into noise: the contour
inverts every time a note crosses the boundary. Instead this module picks one
octave shift per *phrase* and only moves it when it has to, which is the same
shape of problem as the range-switch planner in ``player`` and is solved the
same way -- dynamic programming over a handful of states.

Two structural rules do most of the work:

* Notes that start together keep the same shift, so chords stay chords.
* Changing shift costs far more than being an octave away from the written
  register, so a part that fits under a single shift gets exactly one, and a
  part that does not fit changes shift at the fewest possible places.

The weights below are relative preferences, not measured values. They decide
which compromise is least bad; there is no calibration data behind the
absolute numbers.
"""

from __future__ import annotations

from typing import Sequence


# Notes this close together are treated as one chord and share a shift.
CHORD_WINDOW = 0.03
# A rest at least this long is treated as a phrase boundary, where moving the
# whole part by an octave is much less noticeable.
PHRASE_REST = 0.25

OCTAVE_COST = 20        # per octave away from the written register
SHIFT_COST = 140        # per octave of movement when the shift changes
REST_DISCOUNT = 0.15    # multiplier applied to a change made during a rest

_CANDIDATE_SHIFTS = tuple(range(-48, 49, 12))


class _Cluster:
    __slots__ = ("indices", "start", "end", "low", "high", "shifts")

    def __init__(self, indices: list[int], start: float, end: float,
                 low: int, high: int):
        self.indices = indices
        self.start = start
        self.end = end
        self.low = low
        self.high = high
        self.shifts: tuple[int, ...] = ()


def _feasible(low: int, high: int, range_low: int, range_high: int) -> tuple[int, ...]:
    return tuple(
        shift for shift in _CANDIDATE_SHIFTS
        if range_low <= low + shift and high + shift <= range_high
    )


def _clusters_for_group(notes: Sequence, indices: list[int], transpose: int,
                        range_low: int, range_high: int) -> list[_Cluster]:
    """Group simultaneous notes, splitting any chord too wide to fit at once."""
    indices.sort(key=lambda index: (notes[index].start, notes[index].note))
    clusters: list[_Cluster] = []
    position = 0
    while position < len(indices):
        start = notes[indices[position]].start
        members = [indices[position]]
        position += 1
        while (position < len(indices)
               and notes[indices[position]].start - start < CHORD_WINDOW):
            members.append(indices[position])
            position += 1
        pitches = [notes[index].note + transpose for index in members]
        end = max(notes[index].end for index in members)
        cluster = _Cluster(members, start, end, min(pitches), max(pitches))
        cluster.shifts = _feasible(cluster.low, cluster.high, range_low, range_high)
        if cluster.shifts:
            clusters.append(cluster)
            continue
        # The chord is wider than the sounding range. Nothing can keep it
        # intact, so let its notes move independently and accept the damage.
        for index in members:
            pitch = notes[index].note + transpose
            single = _Cluster([index], notes[index].start, notes[index].end, pitch, pitch)
            single.shifts = _feasible(pitch, pitch, range_low, range_high)
            clusters.append(single)
    clusters.sort(key=lambda item: item.start)
    return clusters


def _solve_run(run: list[_Cluster], shifts: list[int]) -> None:
    """Choose a shift per cluster for one unbroken run of playable clusters."""
    if not run:
        return
    previous: dict[int, int] = {}
    history: list[dict[int, int]] = []
    previous_end: float | None = None

    for cluster in run:
        gap = 0.0 if previous_end is None else cluster.start - previous_end
        factor = REST_DISCOUNT if gap >= PHRASE_REST else 1.0
        scores: dict[int, int] = {}
        choice: dict[int, int] = {}
        for shift in cluster.shifts:
            base = OCTAVE_COST * (abs(shift) // 12)
            if not previous:
                scores[shift] = base
                continue
            best_cost: int | None = None
            best_previous = 0
            for earlier, earlier_cost in previous.items():
                move = abs(shift - earlier) // 12
                cost = earlier_cost + base + round(SHIFT_COST * move * factor)
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_previous = earlier
            scores[shift] = best_cost or 0
            choice[shift] = best_previous
        history.append(choice)
        previous = scores
        previous_end = cluster.end if previous_end is None else max(previous_end, cluster.end)

    shift = min(previous, key=lambda key: previous[key])
    for position in range(len(run) - 1, -1, -1):
        for index in run[position].indices:
            shifts[index] = shift
        shift = history[position].get(shift, shift)


def _solve_group(clusters: list[_Cluster], shifts: list[int]) -> None:
    """Solve each run of reachable clusters; unreachable ones break the run."""
    run: list[_Cluster] = []
    for cluster in clusters:
        if cluster.shifts:
            run.append(cluster)
            continue
        _solve_run(run, shifts)
        run = []
    _solve_run(run, shifts)


def fold_notes(notes: Sequence, transpose: int, range_low: int,
               range_high: int) -> list[int]:
    """Return one octave shift per note, aligned with ``notes``.

    Each MIDI track/channel pair is solved separately so a bass line and a
    melody are free to move by different amounts. Notes that cannot reach the
    range at any octave keep a shift of 0.
    """
    shifts = [0] * len(notes)
    if range_high - range_low < 11:
        return shifts
    groups: dict[tuple[int, int], list[int]] = {}
    for index, note in enumerate(notes):
        groups.setdefault((note.track, note.channel), []).append(index)
    for indices in groups.values():
        clusters = _clusters_for_group(notes, indices, transpose, range_low, range_high)
        _solve_group(clusters, shifts)
    return shifts
