from __future__ import annotations

import inspect
import json

import polars as pl

import polars_ta_lib as pta
from polars_ta_lib import _internal


def test_all_functions_present() -> None:
    assert len(pta.FUNCS) == 237
    assert len(pta.functions()) == 237
    assert len(pta.__all__) == 240  # 237 functions + 3 module attributes


def test_every_function_is_generated() -> None:
    for name, meta in pta.FUNCS.items():
        assert name == meta["python_name"]
        assert getattr(pta, name) is not None
        signature = inspect.signature(getattr(pta, name))
        parameter_names = list(signature.parameters)
        assert len(parameter_names) == len(set(parameter_names))
        fields = [output["field"] for output in meta["outputs"]]
        assert len(fields) == len(set(fields)), name
        assert all(field == field.lower() for field in fields), name


def test_default_columns() -> None:
    sma = inspect.signature(pta.sma).parameters["real"].default
    atr = inspect.signature(pta.atr).parameters
    beta = inspect.signature(pta.beta).parameters

    assert isinstance(sma, pl.Expr)
    assert atr["high"].default is not inspect.Parameter.empty
    assert atr["low"].default is not inspect.Parameter.empty
    assert atr["close"].default is not inspect.Parameter.empty
    assert beta["real0"].default is inspect.Parameter.empty
    assert beta["real1"].default is inspect.Parameter.empty


def test_p1_names() -> None:
    assert [out["field"] for out in pta.FUNCS["macd"]["outputs"]] == [
        "macd",
        "macd_signal",
        "macd_hist",
    ]
    assert [out["field"] for out in pta.FUNCS["bbands"]["outputs"]] == [
        "upper_band",
        "middle_band",
        "lower_band",
    ]
    assert [out["field"] for out in pta.FUNCS["minmaxindex"]["outputs"]] == [
        "min_idx",
        "max_idx",
    ]
    assert pta.FUNCS["atr"]["params"][0]["py_name"] == "time_period"
    assert pta.FUNCS["macdext"]["params"][0]["py_name"] == "fast_period"


def test_metadata_matches_extension() -> None:
    extension = {
        item["python_name"]: item for item in json.loads(_internal.functions_json())
    }
    assert extension.keys() == pta.FUNCS.keys()
    assert extension["macd"] == pta.FUNCS["macd"]


def test_ma_type_accepts_string_and_int() -> None:
    frame = pl.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})
    by_name = frame.select(pta.ma(pl.col("close"), time_period=3, ma_type="sma"))
    by_number = frame.select(pta.ma(pl.col("close"), time_period=3, ma_type=0))
    assert by_name.equals(by_number)
