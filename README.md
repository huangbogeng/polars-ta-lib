# polars_ta_lib

TA-Lib indicators as [Polars](https://pola.rs) expression plugins.

- **237 indicators**, covering all of TA-Lib 0.8.3.
- Pure Rust backend: the official [`ta-lib`](https://crates.io/crates/ta-lib) port. No C toolchain, no `ta_initialize`/`ta_shutdown`.
- One generic Polars expression, driven by TA-Lib's own function metadata.
- Top-level Python functions with conventional column defaults.
- Strict input contract and Polars-native null output.

## Status

Core v1: all 237 functions, generated signatures and docstrings, type stubs, and a test suite that checks every function against `polars-talib-fast` on dense data.

Not yet included: `.ta` expression namespace, `unstable_period`/candle-settings configuration, streaming/incremental APIs, and a Series-level API.

## Install

Requires Python 3.10+, Polars 2.x, and Rust 1.95+ (the Polars dependency graph needs it).

```bash
# from PyPI (once published; PyPI normalizes the name to polars-ta-lib)
pip install polars_ta_lib

# from source
uv venv
uv pip install maturin pytest numpy "polars==2.0.0" "polars-talib-fast==2.0.0"
uv run maturin develop --uv
```

## Usage

```python
import polars as pl
import polars_ta_lib as pta

df = pl.DataFrame(
    {
        "open": [1.0, 2.0, 3.0, 4.0, 5.0],
        "high": [2.0, 3.0, 4.0, 5.0, 6.0],
        "low": [0.5, 1.5, 2.5, 3.5, 4.5],
        "close": [1.0, 2.0, 3.0, 4.0, 5.0],
        "volume": [10.0, 20.0, 30.0, 40.0, 50.0],
    }
)

out = df.with_columns(
    pta.sma(time_period=3).alias("sma3"),
    pta.atr(time_period=3).alias("atr3"),
    pta.macd().struct.field("macd_signal").alias("macd_signal"),
    pta.cdlengulfing().alias("engulfing"),
)
```

### Input defaults

Single-series indicators default to `close`; price components default to the column of the same name. Multiple real inputs are required:

```python
pta.sma(time_period=20)                       # pl.col("close")
pta.atr(time_period=14)                       # high, low, close
pta.cdlengulfing()                            # open, high, low, close
pta.beta(pl.col("a"), pl.col("b"))            # required
```

### Missing values

Inputs must be dense and finite. A null, NaN, or ±Inf raises a `ComputeError` naming the column and position:

```python
df.filter(pl.col("close").is_not_null())
# or
df.with_columns(pl.col("close").forward_fill())
```

The rows before an indicator's lookback are **Polars null**, including integer outputs. `0` is never used as a missing sentinel.

TA-Lib itself may produce NaN or ±Inf for some math transforms (for example `acos` outside `[-1, 1]`); those output values are passed through unchanged.

### Multi-output

Multi-output functions return a `Struct`:

```python
pta.macd()          # macd, macd_signal, macd_hist
pta.bbands()        # upper_band, middle_band, lower_band
pta.minmaxindex()   # min_idx, max_idx
```

Access a field with `.struct.field(...)`, or unnest the column.

### Grouping

Use `.over("symbol")`; the plugin runs once per group and each group starts its own warm-up:

```python
df.with_columns(pta.sma(time_period=20).over("symbol").alias("sma20"))
```

Sort by time within each symbol before computing history-dependent indicators.

### Parameters

Parameter and Struct field names are snake_case. TA-Lib's original names are kept in `pta.FUNCS` for reference. List parameters accept either the numeric value or its name:

```python
pta.ma(time_period=20, ma_type="sma")
pta.ma(time_period=20, ma_type=0)
```

Inspect the generated metadata with:

```python
pta.FUNCS["atr"]
pta.functions()   # all 237 entries
```

## Documentation

The API reference is generated from `pta.FUNCS` and built with MkDocs Material:

```bash
uv pip install mkdocs-material
python tools/generate_docs.py
mkdocs build --strict      # output in site/
# or: mkdocs serve
```

The generator writes one page per TA-Lib group plus `docs/api/index.md`, and copies
`ARCHITECTURE.md` / `PLAN.md` into the site.

## Testing

```bash
uv run pytest -q
```

The suite checks:

- all 237 functions are present and callable;
- default columns and P1 names;
- values against `polars-talib-fast==2.0.0` (both use `ta-lib 0.8.3`);
- grouping, empty/short inputs, multi-chunk inputs, integer/float32 casts;
- strict null/NaN/Inf errors and integer null prefixes.

## License

MIT. TA-Lib is BSD-3-Clause; see `LICENSES/TA-Lib.txt` and `NOTICE`.
