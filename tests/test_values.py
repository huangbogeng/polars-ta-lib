from __future__ import annotations

import polars as pl

import polars_ta_lib as pta


def test_sma_known_values() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    result = frame.select(pta.sma(time_period=3))["close"]
    assert result.to_list() == [None, None, 2.0, 3.0, 4.0]


def test_grouped_matches_per_group(synthetic_frame: pl.DataFrame) -> None:
    grouped = pl.concat(
        [
            synthetic_frame.with_columns(pl.lit("A").alias("symbol")),
            synthetic_frame.with_columns(pl.lit("B").alias("symbol")),
        ]
    )
    over = grouped.select(
        pl.col("symbol"), pta.sma(time_period=5).over("symbol").alias("sma")
    )
    expected = pl.concat(
        [
            grouped.filter(pl.col("symbol") == symbol).select(
                pl.col("symbol"), pta.sma(time_period=5).alias("sma")
            )
            for symbol in ("A", "B")
        ]
    )
    assert over.equals(expected)
