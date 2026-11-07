from __future__ import annotations

import polars as pl
import pytest

import polars_ta_lib as pta


def test_empty_input_returns_empty_typed_series() -> None:
    frame = pl.DataFrame({"close": pl.Series([], dtype=pl.Float64)})
    result = frame.select(pta.sma(time_period=3).alias("sma"))
    assert result.schema["sma"] == pl.Float64
    assert result.height == 0


def test_short_input_is_all_null() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0]})
    result = frame.select(pta.sma(time_period=10).alias("sma"))
    assert result["sma"].to_list() == [None, None, None]


def test_integer_output_has_null_prefix_not_zero() -> None:
    frame = pl.DataFrame(
        {
            "open": [1.0, 2.0, 3.0, 4.0],
            "high": [2.0, 3.0, 4.0, 5.0],
            "low": [0.5, 1.5, 2.5, 3.5],
            "close": [1.0, 2.0, 3.0, 4.0],
        }
    )
    result = frame.select(pta.cdlengulfing().alias("cdl"))
    assert result.schema["cdl"] == pl.Int32
    assert result["cdl"].to_list()[:2] == [None, None]


def test_minmaxindex_positions() -> None:
    frame = pl.DataFrame({"close": [1.0, 3.0, 2.0, 4.0, 0.0, 5.0]})
    result = frame.select(pta.minmaxindex(time_period=3).alias("mm")).unnest("mm")
    assert result.columns == ["min_idx", "max_idx"]
    assert result.schema == {"min_idx": pl.Int32, "max_idx": pl.Int32}
    assert result["min_idx"].to_list()[:2] == [None, None]


def test_multi_chunk_matches_single_chunk() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    chunked = pl.concat([frame.head(2), frame.tail(4)], rechunk=False)
    single = frame.select(pta.sma(time_period=3).alias("sma"))
    multi = chunked.select(pta.sma(time_period=3).alias("sma"))
    assert single.equals(multi)


def test_integer_and_float32_inputs_are_cast() -> None:
    frame = pl.DataFrame(
        {
            "close": pl.Series([1, 2, 3, 4], dtype=pl.Int32),
            "other": pl.Series([1.0, 2.0, 3.0, 4.0], dtype=pl.Float32),
        }
    )
    result = frame.select(
        pta.sma(pl.col("close"), time_period=2).alias("int_input"),
        pta.sma(pl.col("other"), time_period=2).alias("f32_input"),
    )
    assert result["int_input"].to_list() == [None, 1.5, 2.5, 3.5]
    assert result["f32_input"].to_list() == [None, 1.5, 2.5, 3.5]


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), float("-inf")])
def test_null_and_non_finite_inputs_raise(bad: float | None) -> None:
    frame = pl.DataFrame({"close": [1.0, bad, 3.0]})
    with pytest.raises(pl.exceptions.ComputeError) as exc:
        frame.select(pta.sma(time_period=2))
    message = str(exc.value)
    assert "close" in message
    assert "null" in message or "non-finite" in message


def test_non_numeric_input_is_rejected() -> None:
    frame = pl.DataFrame({"close": ["1.0", "2.0", "3.0"]})
    with pytest.raises(pl.exceptions.ComputeError, match="numeric"):
        frame.select(pta.sma(time_period=2))


def test_invalid_parameter_is_rejected_before_the_plugin() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="time_period"):
        frame.select(pta.sma(time_period=0))


def test_multiple_real_inputs_must_be_explicit() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(TypeError):
        frame.select(pta.beta(pl.col("close")))


def test_missing_default_column_raises() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0]})
    with pytest.raises(Exception):
        frame.select(pta.atr(time_period=2))
