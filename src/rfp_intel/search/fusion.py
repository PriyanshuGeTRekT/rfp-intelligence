"""Reciprocal rank fusion.

Fusion runs in Python rather than inside Qdrant so that k and per-list weights are explicit,
every list's ranks can be reported per hit, and the same code fuses lists from any backend.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class RankedList:
    name: str
    chunk_ids: Sequence[str]
    weight: float = 1.0


@dataclass
class Fused:
    chunk_id: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # list name -> 1-based rank


def rrf(lists: Sequence[RankedList], k: int = 60) -> list[Fused]:
    """score(d) = sum over lists of weight / (k + rank(d)); ties keep first-seen order."""
    fused: dict[str, Fused] = {}
    for ranked in lists:
        for rank, chunk_id in enumerate(ranked.chunk_ids, start=1):
            entry = fused.setdefault(chunk_id, Fused(chunk_id, 0.0))
            if ranked.name in entry.ranks:
                continue  # a list naming the same chunk twice counts once
            entry.score += ranked.weight / (k + rank)
            entry.ranks[ranked.name] = rank
    return sorted(fused.values(), key=lambda f: f.score, reverse=True)
