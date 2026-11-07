from __future__ import annotations

import math

import polars as pl
import pytest

N = 300


def make_frame() -> pl.DataFrame:
    rows = []
    for i in range(N):
        base = 100.0 + i * 0.05 + math.sin(i / 7.0)
        rows.append(
            {
                "open": base + 0.1 * math.cos(i / 5.0),
                "high": base + 1.0 + 0.2 * math.sin(i / 3.0),
                "low": base - 1.0 - 0.2 * math.cos(i / 4.0),
                "close": base + 0.3 * math.sin(i / 6.0),
                "volume": 1000.0 + 10.0 * (i % 17),
                "periods": 5.0,
            }
        )
    return pl.DataFrame(rows)


@pytest.fixture(scope="session")
def synthetic_frame() -> pl.DataFrame:
    return make_frame()
