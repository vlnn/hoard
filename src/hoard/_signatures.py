from __future__ import annotations

import random
from array import array
from functools import lru_cache
from operator import itemgetter
from typing import Callable, NamedTuple

BITS = 128
SPARSITY = 3


class Plane(NamedTuple):
    plus: Callable
    minus: Callable

    def side(self, values: list) -> bool:
        return sum(self.plus(values)) > sum(self.minus(values))


def picker(indices: list, zero: int) -> Callable:
    # the trailing zero keeps itemgetter returning a tuple however few indices a plane draws
    return itemgetter(zero, zero, *indices)


def plane(rng: random.Random, dimensions: int) -> Plane:
    draws = [rng.randrange(2 * SPARSITY) for _ in range(dimensions)]
    chosen = [[index for index, draw in enumerate(draws) if draw == side] for side in (0, 1)]
    return Plane(*(picker(indices, dimensions) for indices in chosen))


@lru_cache(maxsize=4)
def planes(dimensions: int) -> tuple:
    rng = random.Random(dimensions)
    return tuple(plane(rng, dimensions) for _ in range(BITS))


def of(vector: array) -> bytes:
    values = vector.tolist() + [0.0]
    bits = sum(1 << n for n, each in enumerate(planes(len(vector))) if each.side(values))
    return bits.to_bytes(BITS // 8, "big")


def number(signature: bytes) -> int:
    return int.from_bytes(signature, "big")


def bits_apart(origin: int, other: bytes) -> int:
    return bin(origin ^ number(other)).count("1")


def distance(one: bytes, other: bytes) -> int:
    return bits_apart(number(one), other)
