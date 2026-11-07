#!/usr/bin/env python3
"""Regenerate the golden regression fixtures used by ``tests/test_golden.py``.

Run from the repository root with an installed ``polars_ta_lib``:

    python tools/generate_golden.py

Only regenerate when an intentional indicator-output change is made; the
fixture is a regression snapshot, not an independent oracle.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import polars as pl

import polars_ta_lib as pta

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
N = 300

PARAM_CASES = {
    "sma_10": {"func": "SMA", "params": {"time_period": 10}},
    "bbands_5": {
        "func": "BBANDS",
        "params": {
            "time_period": 5,
            "nb_dev_up": 2.0,
            "nb_dev_dn": 2.0,
            "ma_type": 1,
        },
    },
    "macd_5_10_3": {
        "func": "MACD",
        "params": {"fast_period": 5, "slow_period": 10, "signal_period": 3},
    },
    "stoch_5_3": {
        "func": "STOCH",
        "params": {
            "fast_k_period": 5,
            "slow_k_period": 3,
            "slow_k_ma_type": 0,
            "slow_d_period": 3,
            "slow_d_ma_type": 0,
        },
    },
}


def synthetic_frame() -> pl.DataFrame:
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


def flat_inputs(meta: dict) -> list[str]:
    names: list[str] = []
    for item in meta["inputs"]:
        if item["kind"] == "price":
            names.extend(component["name"] for component in item["components"])
        else:
            names.append(item["py_name"])
    return names


def expr(name: str) -> pl.Expr:
    if name in ("real", "real0"):
        return pl.col("close")
    if name == "real1":
        return pl.col("open")
    if name == "periods":
        return pl.col("periods")
    return pl.col(name)


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    frame = synthetic_frame()
    arrays: dict[str, np.ndarray] = {}
    outputs: list[dict] = []
    index = 0

    for meta in pta.FUNCS.values():
        cases = [("default", {})]
        cases.extend(
            (name, case["params"])
            for name, case in PARAM_CASES.items()
            if case["func"] == meta["name"]
        )
        inputs = [expr(name) for name in flat_inputs(meta)]
        fn = getattr(pta, meta["python_name"])

        for case, params in cases:
            result = frame.select(fn(*inputs, **params).alias("out"))
            dtype = result.schema["out"]
            if isinstance(dtype, pl.Struct):
                unfolded = result.unnest("out")
                fields = unfolded.columns
            else:
                unfolded = result
                fields = ["out"]

            for field in fields:
                series = unfolded[field]
                valid = np.asarray(series.is_not_null().to_numpy(), dtype=bool)
                if series.dtype == pl.Float64:
                    values = np.asarray(series.to_numpy(), dtype=np.float64)
                    dtype_name = "float64"
                else:
                    values = np.asarray(series.fill_null(0).to_numpy(), dtype=np.int32)
                    dtype_name = "int32"

                value_key = f"v{index}"
                valid_key = f"m{index}"
                arrays[value_key] = values
                arrays[valid_key] = valid
                outputs.append(
                    {
                        "func": meta["name"],
                        "python_name": meta["python_name"],
                        "case": case,
                        "params": params,
                        "field": field,
                        "dtype": dtype_name,
                        "values_key": value_key,
                        "valid_key": valid_key,
                    }
                )
                index += 1

    np.savez_compressed(GOLDEN / "expected.npz", **arrays)
    (GOLDEN / "manifest.json").write_text(
        json.dumps({"outputs": outputs}, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(outputs)} output arrays to {GOLDEN}")


if __name__ == "__main__":
    main()
