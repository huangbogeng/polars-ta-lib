from __future__ import annotations

import polars as pl
import pytest
from polars.testing import assert_series_equal

import polars_ta_lib as pta


def _our_flat(meta: dict) -> list[str]:
    names: list[str] = []
    for item in meta["inputs"]:
        if item["kind"] == "price":
            names.extend(component["name"] for component in item["components"])
        else:
            names.append(item["py_name"])
    return names


def _fast_flat(meta: dict) -> list[str]:
    names: list[str] = []
    for name, parts in meta["inputs"]:
        names.extend(parts if parts else [name])
    return names


def _expr(name: str) -> pl.Expr:
    if name in ("real", "real0"):
        return pl.col("close")
    if name == "real1":
        return pl.col("open")
    if name == "periods":
        return pl.col("periods")
    return pl.col(name)


def _normalize(series: pl.Series) -> pl.Series:
    return series.fill_nan(None) if series.dtype == pl.Float64 else series


def _compare(ours: pl.Series, theirs: pl.Series) -> None:
    ours = _normalize(ours)
    theirs = _normalize(theirs)
    mask = ours.is_not_null()
    if mask.any():
        assert_series_equal(
            ours.filter(mask),
            theirs.filter(mask),
            check_exact=True,
            check_names=False,
            check_dtypes=True,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )


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


def test_parameters_match_fast(synthetic_frame: pl.DataFrame) -> None:
    fast = pytest.importorskip("polars_talib_fast")
    from polars_talib_fast._polars_talib_fast import functions as fast_functions

    fast_metas = {item["name"]: item for item in fast_functions()}
    cases = {
        "SMA": {"time_period": 10},
        "BBANDS": {"time_period": 5, "nb_dev_up": 2.0, "nb_dev_dn": 2.0, "ma_type": 1},
        "MACD": {"fast_period": 5, "slow_period": 10, "signal_period": 3},
        "STOCH": {
            "fast_k_period": 5,
            "slow_k_period": 3,
            "slow_k_ma_type": 0,
            "slow_d_period": 3,
            "slow_d_ma_type": 0,
        },
    }

    for name, our_params in cases.items():
        meta = pta.FUNCS[name.lower()]
        fast_meta = fast_metas[name]
        fast_params = {
            fast_param[0]: value
            for our_param, fast_param in zip(meta["params"], fast_meta["params"])
            if (value := our_params.get(our_param["py_name"])) is not None
        }
        ours = synthetic_frame.select(
            getattr(pta, meta["python_name"])(
                *[_expr(n) for n in _our_flat(meta)], **our_params
            ).alias("out")
        )
        theirs = synthetic_frame.select(
            getattr(fast, meta["python_name"])(
                **{n: _expr(n) for n in _fast_flat(fast_meta)}, **fast_params
            ).alias("out")
        )
        if isinstance(ours.schema["out"], pl.Struct):
            ours_u = ours.unnest("out")
            theirs_u = theirs.unnest("out")
            for left, right in zip(ours_u.columns, theirs_u.columns):
                _compare(ours_u[left], theirs_u[right])
        else:
            _compare(ours["out"], theirs["out"])


def test_parity_with_fast(synthetic_frame: pl.DataFrame) -> None:
    fast = pytest.importorskip("polars_talib_fast")
    from polars_talib_fast._polars_talib_fast import functions as fast_functions

    fast_metas = {item["name"]: item for item in fast_functions()}
    failures: list[str] = []

    for meta in pta.FUNCS.values():
        name = meta["name"]
        fast_meta = fast_metas.get(name)
        if fast_meta is None:
            failures.append(f"{name}: missing in fast")
            continue
        try:
            ours = synthetic_frame.select(
                getattr(pta, meta["python_name"])(
                    *[_expr(n) for n in _our_flat(meta)]
                ).alias("out")
            )
            theirs = synthetic_frame.select(
                getattr(fast, meta["python_name"])(
                    **{n: _expr(n) for n in _fast_flat(fast_meta)}
                ).alias("out")
            )

            ours_dtype = ours.schema["out"]
            theirs_dtype = theirs.schema["out"]
            if isinstance(ours_dtype, pl.Struct):
                assert isinstance(theirs_dtype, pl.Struct), f"{name}: dtype"
                ours_u = ours.unnest("out")
                theirs_u = theirs.unnest("out")
                assert len(ours_u.columns) == len(theirs_u.columns), f"{name}: fields"
                for left, right in zip(ours_u.columns, theirs_u.columns):
                    assert ours_u[left].dtype == theirs_u[right].dtype, f"{name}: {left}"
                    _compare(ours_u[left], theirs_u[right])
            else:
                assert ours_dtype == theirs_dtype, f"{name}: dtype"
                _compare(ours["out"], theirs["out"])
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not failures, "\n".join(failures[:20])
