"""A robot's trail: its newest points, each tagged with the seq it was added at."""

from array import array
from typing import Dict, Iterator, List, Optional, Union

from dotbot.models import MAX_TRAIL_SIZE, DotBotGPSPosition, DotBotLH2Position

LH2 = 0
GPS = 1

Point = Union[DotBotLH2Position, DotBotGPSPosition]


class Trail:
    """At most `maxlen` points, oldest first, as a ring of plain arrays.

    A point is its seq, its kind (`LH2` or `GPS`) and two coordinates: x
    and y in mm, or latitude and longitude. Model objects and JSON values
    are built only when read.
    """

    __slots__ = ("maxlen", "_seqs", "_kinds", "_a", "_b", "_head")

    def __init__(self, maxlen: int = MAX_TRAIL_SIZE):
        self.maxlen = maxlen
        self._seqs = array("q")
        self._kinds = array("b")
        self._a = array("d")
        self._b = array("d")
        # Index of the oldest point once the ring is full
        self._head = 0

    def __len__(self) -> int:
        return len(self._seqs)

    def append(self, seq: int, point: Point) -> Optional[int]:
        """Add `point` at `seq`; the seq of the point it pushed out, if any."""
        if isinstance(point, DotBotGPSPosition):
            kind, a, b = GPS, point.latitude, point.longitude
        else:
            kind, a, b = LH2, point.x, point.y
        if len(self._seqs) < self.maxlen:
            self._seqs.append(seq)
            self._kinds.append(kind)
            self._a.append(a)
            self._b.append(b)
            return None
        head = self._head
        evicted = self._seqs[head]
        self._seqs[head], self._kinds[head] = seq, kind
        self._a[head], self._b[head] = a, b
        self._head = (head + 1) % self.maxlen
        return evicted

    def clear(self) -> None:
        for column in (self._seqs, self._kinds, self._a, self._b):
            del column[:]
        self._head = 0

    def _index(self, age: int) -> int:
        """Where the point `age` places from the newest (0) is stored."""
        return (self._head + len(self._seqs) - 1 - age) % len(self._seqs)

    def last(self) -> Optional[Point]:
        """The newest point, or None."""
        if not self._seqs:
            return None
        return self._model(self._index(0))

    def _newest_first(self) -> Iterator[int]:
        for age in range(len(self._seqs)):
            yield self._index(age)

    def _model(self, i: int) -> Point:
        if self._kinds[i] == GPS:
            return DotBotGPSPosition(latitude=self._a[i], longitude=self._b[i])
        return DotBotLH2Position(x=self._a[i], y=self._b[i])

    def _json(self, i: int) -> Dict[str, float]:
        if self._kinds[i] == GPS:
            return {"latitude": self._a[i], "longitude": self._b[i]}
        return {"x": self._a[i], "y": self._b[i]}

    def _pick(
        self, count: Optional[int], upto: Optional[int], after: int
    ) -> List[int]:
        """The indices of the newest `count` points with a seq in
        (`after`, `upto`], oldest first."""
        picked = []
        seqs = self._seqs
        for i in self._newest_first():
            seq = seqs[i]
            if seq <= after or count == len(picked):
                break
            if upto is not None and seq > upto:
                continue
            picked.append(i)
        picked.reverse()
        return picked

    def json(
        self, count: Optional[int] = None, upto: Optional[int] = None, after: int = -1
    ) -> List[Dict[str, float]]:
        """The newest `count` points added after seq `after` and no later
        than `upto`, oldest first, as JSON values."""
        return [self._json(i) for i in self._pick(count, upto, after)]

    def models(self, count: Optional[int] = None) -> List[Point]:
        """The newest `count` points, oldest first, as models."""
        return [self._model(i) for i in self._pick(count, None, -1)]
