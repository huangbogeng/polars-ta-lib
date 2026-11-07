# Changelog

## 0.1.0 - 2026-11-07

### Added

- All 237 TA-Lib 0.8.3 indicators as top-level Polars expressions.
- Pure-Rust backend using the official `ta-lib` crate; no C toolchain.
- Conventional input defaults (`close`, `high`, `low`, …), with explicit
  inputs required for multiple real series.
- Polars-native null warm-up rows for `Float64` and `Int32` outputs.
- Strict input validation: numeric, dense, finite columns only.
- Multi-output indicators returned as `Struct` with Pythonic field names.
- Generated signatures, docstrings, type stubs, and `FUNCS` metadata.
- MkDocs Material API reference generated from TA-Lib metadata.
- abi3 wheel build, CI matrix, and 24-test suite including 237-function parity
  against `polars-talib-fast==2.0.0`.
- Tested with Polars 1.44.2 (Python 3.10), 2.0.0 (Python 3.10), and 2.1.0
  (Python 3.12).

### Notes

- `.ta` expression namespace is deferred.
- `unstable_period` / candle-settings configuration is deferred.
- Streaming and Series-level APIs are deferred.
