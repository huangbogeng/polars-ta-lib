"""Build the public API from TA-Lib's own function metadata.

Nothing here hard-codes an indicator, its parameters or its defaults: every
function is generated from ``_internal.functions_json()``.
"""

from __future__ import annotations

import inspect
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import polars as pl
from polars.plugins import register_plugin_function

from . import _internal

PLUGIN = Path(__file__).parent

_METADATA: list[dict[str, Any]] = json.loads(_internal.functions_json())


@dataclass(frozen=True)
class SeriesArg:
    name: str
    default: str | None


@dataclass(frozen=True)
class Param:
    raw_name: str
    name: str
    display_name: str
    hint: str
    kind: str
    minimum: float | None
    maximum: float | None
    default: int | float
    values: tuple[tuple[float, str], ...] | None


@dataclass(frozen=True)
class Spec:
    name: str
    python_name: str
    group: str
    hint: str
    series: tuple[SeriesArg, ...]
    params: tuple[Param, ...]
    outputs: tuple[dict[str, str], ...]

    @classmethod
    def from_meta(cls, meta: dict[str, Any]) -> Spec:
        series: list[SeriesArg] = []
        for item in meta["inputs"]:
            if item["kind"] == "real" or item["kind"] == "integer":
                series.append(SeriesArg(item["py_name"], item["default"]))
            elif item["kind"] == "price":
                series.extend(
                    SeriesArg(component["name"], component["default"])
                    for component in item["components"]
                )
            else:
                raise RuntimeError(f"{meta['name']}: unknown input kind {item['kind']!r}")

        params: list[Param] = []
        for item in meta["params"]:
            integer = item["kind"].startswith("int")
            default = int(item["default"]) if integer else float(item["default"])
            values = (
                tuple((float(value), display) for value, display in item["values"])
                if item["values"] is not None
                else None
            )
            params.append(
                Param(
                    raw_name=item["raw_name"],
                    name=item["py_name"],
                    display_name=item["display_name"],
                    hint=item["hint"],
                    kind=item["kind"],
                    minimum=item["min"],
                    maximum=item["max"],
                    default=default,
                    values=values,
                )
            )

        return cls(
            name=meta["name"],
            python_name=meta["python_name"],
            group=meta["group"],
            hint=meta["hint"],
            series=tuple(series),
            params=tuple(params),
            outputs=tuple(meta["outputs"]),
        )

    @property
    def doc(self) -> str:
        lines = [f"{self.hint} ({self.group}), TA-Lib {self.name}.", "", "Inputs:"]
        lines.extend(
            f"    {arg.name}: {arg.default or 'required'}" for arg in self.series
        )
        if self.params:
            lines.append("Parameters:")
            for param in self.params:
                if param.kind in ("int_list", "real_list") and param.values:
                    allowed = ", ".join(display for _, display in param.values)
                    lines.append(
                        f"    {param.name}: {param.default} ({param.hint}; one of {allowed})"
                    )
                else:
                    lines.append(f"    {param.name}: {param.default} ({param.hint})")
        fields = ", ".join(output["field"] for output in self.outputs)
        lines.append("Output struct fields: " + fields if len(self.outputs) > 1 else f"Output: {fields}")
        return "\n".join(lines)


SPECS: tuple[Spec, ...] = tuple(Spec.from_meta(meta) for meta in _METADATA)
FUNCS: dict[str, dict[str, Any]] = {
    meta["python_name"]: meta for meta in _METADATA
}


def functions() -> list[dict[str, Any]]:
    """Return the metadata of every TA-Lib function as plain dictionaries."""
    return list(_METADATA)


def signature(spec: Spec) -> inspect.Signature:
    parameters: list[inspect.Parameter] = []

    for arg in spec.series:
        default = (
            inspect.Parameter.empty if arg.default is None else pl.col(arg.default)
        )
        parameters.append(
            inspect.Parameter(
                arg.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=pl.Expr,
            )
        )

    for param in spec.params:
        annotation = int if param.kind.startswith("int") else float
        parameters.append(
            inspect.Parameter(
                param.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=param.default,
                annotation=annotation,
            )
        )

    return inspect.Signature(parameters, return_annotation=pl.Expr)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _list_value(param: Param, text: str) -> float:
    assert param.values is not None
    key = _normalize(text)
    for value, display in param.values:
        numeric = str(int(value)) if float(value).is_integer() else str(value)
        if _normalize(display) == key or _normalize(numeric) == key:
            return value
    allowed = ", ".join(display for _, display in param.values)
    raise ValueError(f"{param.name}: expected one of {allowed}, got {text!r}")


def _coerce(param: Param, value: Any) -> int | float:
    if value is None:
        value = param.default

    if param.kind == "int_range":
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{param.name}: expected int, got {type(value).__name__}")
        if param.minimum is not None and value < param.minimum:
            raise ValueError(f"{param.name}: {value} below minimum {param.minimum:g}")
        if param.maximum is not None and value > param.maximum:
            raise ValueError(f"{param.name}: {value} above maximum {param.maximum:g}")
        return value

    if param.kind == "int_list":
        if isinstance(value, str):
            numeric = _list_value(param, value)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"{param.name}: expected int or name, got {type(value).__name__}"
            )
        else:
            numeric = float(value)
        assert param.values is not None
        if not any(math.isclose(numeric, allowed, abs_tol=1e-12) for allowed, _ in param.values):
            allowed = ", ".join(display for _, display in param.values)
            raise ValueError(f"{param.name}: expected one of {allowed}, got {value!r}")
        return int(round(numeric))

    if param.kind == "real_range":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{param.name}: expected a real number, got {type(value).__name__}")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{param.name}: expected a finite number")
        if param.minimum is not None and numeric < param.minimum:
            raise ValueError(f"{param.name}: {numeric:g} below minimum {param.minimum:g}")
        if param.maximum is not None and numeric > param.maximum:
            raise ValueError(f"{param.name}: {numeric:g} above maximum {param.maximum:g}")
        return numeric

    if param.kind == "real_list":
        if isinstance(value, str):
            numeric = _list_value(param, value)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"{param.name}: expected a real number or name, got {type(value).__name__}"
            )
        else:
            numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{param.name}: expected a finite number")
        assert param.values is not None
        if not any(math.isclose(numeric, allowed, abs_tol=1e-12) for allowed, _ in param.values):
            allowed = ", ".join(display for _, display in param.values)
            raise ValueError(f"{param.name}: expected one of {allowed}, got {value!r}")
        return numeric

    raise RuntimeError(f"{param.name}: unknown parameter kind {param.kind!r}")


def function(spec: Spec) -> Callable[..., pl.Expr]:
    signature_ = signature(spec)
    width = len(spec.series)

    def generated(*args: Any, **kwargs: Any) -> pl.Expr:
        bound = signature_.bind(*args, **kwargs)
        bound.apply_defaults()
        values = list(bound.arguments.values())
        series = values[:width]
        params = [
            _coerce(param, value)
            for param, value in zip(spec.params, values[width:], strict=True)
        ]
        return register_plugin_function(
            plugin_path=PLUGIN,
            function_name="call",
            args=series,
            kwargs={"name": spec.name, "params": params},
            is_elementwise=False,
        )

    generated.__name__ = spec.python_name
    generated.__qualname__ = spec.python_name
    generated.__module__ = __name__
    generated.__doc__ = spec.doc
    generated.__signature__ = signature_  # type: ignore[attr-defined]
    return generated


def build_all() -> dict[str, Callable[..., pl.Expr]]:
    """Build every generated function, keyed by its Python name."""
    return {spec.python_name: function(spec) for spec in SPECS}
