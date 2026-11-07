# polars_ta_lib

TA-Lib indicators as Polars expression plugins.

- **237 indicators**, covering all of TA-Lib 0.8.3.
- Pure Rust backend: the official [`ta-lib`](https://crates.io/crates/ta-lib) port. No C toolchain.
- One generic Polars expression, driven by TA-Lib's own metadata.
- Top-level Python functions with conventional column defaults.
- Strict input contract and Polars-native null output.

## Install

```bash
# from PyPI (once published; PyPI normalizes the name to polars-ta-lib)
pip install polars_ta_lib

# from source
uv venv
uv pip install maturin "polars>=1.44,<3"
uv run maturin develop --uv
```

Polars 1.44+ is supported. Polars 2.1 requires Python 3.11+, so Python 3.10
resolves to Polars 1.44–2.0.

## Quick start

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

## Semantics

- Single-series indicators default to `close`; price components default to the column of the same name; multiple real inputs are required.
- Inputs must be dense and finite. Null, NaN, or ±Inf raises a `ComputeError` naming the column and position.
- Rows before an indicator's lookback are Polars null, including integer outputs. `0` is never a missing sentinel.
- Multi-output functions return a `Struct`.

## More

- [API Reference](api/index.md)
- [Architecture](architecture.md)
- [Implementation Plan](plan.md)
