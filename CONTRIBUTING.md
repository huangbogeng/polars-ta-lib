# Contributing

Thanks for helping improve `polars_ta_lib`.

## Setup

```bash
uv venv
uv pip install maturin pytest numpy "polars>=1.44,<3" "polars-talib-fast==2.0.0"
uv run maturin develop --uv
```

Requires Rust 1.95+ (see `rust-toolchain.toml`), Python 3.10+, and Polars 1.44+.

## Build and test

```bash
uv run maturin develop --uv
uv run pytest -q
cargo fmt --check
cargo clippy --all-targets -- -D warnings
```

The test suite checks all 237 functions against `polars-talib-fast==2.0.0` on
dense finite data, plus grouping, empty/short inputs, multi-chunk inputs, and
the strict null/NaN/Inf contract.

## Documentation

```bash
uv pip install "mkdocs>=1.6,<2" mkdocs-material
python tools/generate_docs.py
mkdocs build --strict
```

API pages are generated from `pta.FUNCS`; do not edit `docs/api/` by hand.

## Pull requests

- Keep one logical change per PR.
- Add or update tests for behavior changes.
- Run formatting, clippy, pytest, and the docs build.
- Update `CHANGELOG.md` for user-visible changes.
- Do not commit `target/`, `dist/`, `site/`, or generated `docs/api/` pages.
