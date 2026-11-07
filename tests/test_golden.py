from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

import polars_ta_lib as pta

GOLDEN = Path(__file__).parent / "golden"
MANIFEST = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))


def _flat_inputs(meta: dict) -> list[str]:
    names: list[str] = []
    for item in meta["inputs"]:
        if item["kind"] == "price":
            names.extend(component["name"] for component in item["components"])
        else:
            names.append(item["py_name"])
    return names


def _expr(name: str) -> pl.Expr:
    if name in ("real", "real0"):
        return pl.col("close")
    if name == "real1":
        return pl.col("open")
    if name == "periods":
        return pl.col("periods")
    return pl.col(name)


def test_golden_outputs(synthetic_frame: pl.DataFrame) -> None:
    data = np.load(GOLDEN / "expected.npz")
    cache: dict[tuple[str, str], pl.DataFrame] = {}

    for entry in MANIFEST["outputs"]:
        key = (entry["func"], entry["case"])
        if key not in cache:
            meta = pta.FUNCS[entry["python_name"]]
            inputs = [_expr(name) for name in _flat_inputs(meta)]
            cache[key] = synthetic_frame.select(
                getattr(pta, meta["python_name"])(*inputs, **entry["params"]).alias("out")
            )

        result = cache[key]
        if isinstance(result.schema["out"], pl.Struct):
            series = result.unnest("out")[entry["field"]]
        else:
            series = result["out"]

        expected_dtype = pl.Float64 if entry["dtype"] == "float64" else pl.Int32
        assert series.dtype == expected_dtype, entry

        validity = np.asarray(series.is_not_null().to_numpy(), dtype=bool)
        expected_validity = data[entry["valid_key"]]
        np.testing.assert_array_equal(validity, expected_validity, err_msg=str(entry))

        if expected_dtype == pl.Float64:
            values = np.asarray(series.to_numpy(), dtype=np.float64)
        else:
            values = np.asarray(series.fill_null(0).to_numpy(), dtype=np.int32)

        expected_values = data[entry["values_key"]]
        mask = expected_validity
        actual = values[mask]
        expected = expected_values[mask]

        if expected_dtype == pl.Float64:
            actual_nan = np.isnan(actual)
            expected_nan = np.isnan(expected)
            np.testing.assert_array_equal(actual_nan, expected_nan, err_msg=str(entry))
            finite = ~expected_nan
            np.testing.assert_allclose(
                actual[finite],
                expected[finite],
                rtol=1e-12,
                atol=1e-12,
                err_msg=str(entry),
            )
        else:
            np.testing.assert_array_equal(actual, expected, err_msg=str(entry))
