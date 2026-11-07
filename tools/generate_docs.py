#!/usr/bin/env python3
"""Generate the MkDocs API reference from ``polars_ta_lib.FUNCS``.

Run after the extension is installed (``maturin develop`` or a wheel):

    python tools/generate_docs.py

The generated pages are input to ``mkdocs build``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars_ta_lib as pta

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
API = DOCS / "api"

GROUPS = [
    "Cycle Indicators",
    "Math Operators",
    "Math Transform",
    "Momentum Indicators",
    "Overlap Studies",
    "Pattern Recognition",
    "Price Transform",
    "Statistic Functions",
    "Volatility Indicators",
    "Volume Indicators",
]


def slug(group: str) -> str:
    return group.lower().replace(" ", "-")


def flat_inputs(meta: dict) -> list[tuple[str, str | None]]:
    inputs: list[tuple[str, str | None]] = []
    for item in meta["inputs"]:
        if item["kind"] == "price":
            inputs.extend((component["name"], component["default"]) for component in item["components"])
        else:
            inputs.append((item["py_name"], item["default"]))
    return inputs


def fmt_default(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def signature_text(meta: dict) -> str:
    parts: list[str] = []
    for name, default in flat_inputs(meta):
        if default is None:
            parts.append(name)
        else:
            parts.append(f'{name}=pl.col("{default}")')
    for param in meta["params"]:
        parts.append(f'{param["py_name"]}={fmt_default(param["default"])}')
    return f"pta.{meta['python_name']}({', '.join(parts)})"


def example_text(meta: dict) -> str:
    args: list[str] = []
    for name, default in flat_inputs(meta):
        if default is None:
            if name == "real1":
                args.append('pl.col("open")')
            else:
                args.append('pl.col("close")')
    for param in meta["params"]:
        if param["py_name"] == "time_period":
            args.append("time_period=20")
    call = f"pta.{meta['python_name']}({', '.join(args)})"
    if len(meta["outputs"]) == 1:
        return f'df.select({call}.alias("{meta["python_name"]}"))'
    return f'df.select({call}.alias("out")).unnest("out")'


def inputs_table(meta: dict) -> str:
    lines = ["| Input | Default |", "|---|---|"]
    for name, default in flat_inputs(meta):
        shown = f'`pl.col("{default}")`' if default else "required"
        lines.append(f"| `{name}` | {shown} |")
    return "\n".join(lines)


def params_table(meta: dict) -> str:
    if not meta["params"]:
        return "None."
    lines = [
        "| Parameter | TA-Lib name | Type | Default | Range / values |",
        "|---|---|---|---|---|",
    ]
    for param in meta["params"]:
        kind = param["kind"]
        if kind in ("int_list", "real_list"):
            kind_text = "int or name" if kind == "int_list" else "float or name"
        else:
            kind_text = "int" if kind == "int_range" else "float"
        if param["values"]:
            allowed = ", ".join(display for _, display in param["values"])
        elif param["min"] is not None and param["max"] is not None:
            allowed = f'{param["min"]:g} .. {param["max"]:g}'
        else:
            allowed = "any"
        lines.append(
            f'| `{param["py_name"]}` | `{param["raw_name"]}` | {kind_text} | '
            f'{fmt_default(param["default"])} | {allowed} |'
        )
    return "\n".join(lines)


def outputs_table(meta: dict) -> str:
    lines = ["| Field | dtype |", "|---|---|"]
    for output in meta["outputs"]:
        dtype = "Float64" if output["dtype"] == "float64" else "Int32"
        lines.append(f'| `{output["field"]}` | {dtype} |')
    return "\n".join(lines)


def group_page(group: str, functions: list[dict]) -> str:
    lines = [
        f"# {group}",
        "",
        "[Back to API overview](index.md)",
        "",
        f"{len(functions)} functions.",
        "",
    ]
    for meta in functions:
        lines.extend(
            [
                f'## `pta.{meta["python_name"]}`',
                "",
                meta["hint"],
                "",
                "```python",
                signature_text(meta),
                "```",
                "",
                f'**TA-Lib name:** `{meta["name"]}`',
                "",
                "### Inputs",
                "",
                inputs_table(meta),
                "",
                "### Parameters",
                "",
                params_table(meta),
                "",
                "### Outputs",
                "",
                outputs_table(meta),
                "",
            ]
        )
        if len(meta["outputs"]) > 1:
            lines.extend(["Returned as a `Struct`.", ""])
        lines.extend(
            [
                "### Example",
                "",
                "```python",
                example_text(meta),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def index_page(groups: dict[str, list[dict]]) -> str:
    lines = [
        "# API Reference",
        "",
        "All TA-Lib 0.8.3 functions, exposed as top-level Polars expressions.",
        "",
        "| Group | Functions |",
        "|---|---:|",
    ]
    for group in GROUPS:
        lines.append(f"| [{group}]({slug(group)}.md) | {len(groups[group])} |")
    lines.extend(
        [
            "",
            "Every function accepts an optional set of parameters; defaults are shown in its page. "
            "Inputs default to the conventional columns (`close`, `high`, `low`, …); multiple real "
            "inputs must be supplied explicitly.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    API.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict]] = {group: [] for group in GROUPS}
    for meta in pta.FUNCS.values():
        groups.setdefault(meta["group"], []).append(meta)

    for group in GROUPS:
        functions = sorted(groups[group], key=lambda item: item["python_name"])
        (API / f"{slug(group)}.md").write_text(group_page(group, functions), encoding="utf-8")

    (API / "index.md").write_text(index_page(groups), encoding="utf-8")
    shutil.copyfile(ROOT / "ARCHITECTURE.md", DOCS / "architecture.md")
    shutil.copyfile(ROOT / "PLAN.md", DOCS / "plan.md")
    print(f"generated {len(pta.FUNCS)} functions in {len(GROUPS)} group pages")


if __name__ == "__main__":
    main()
