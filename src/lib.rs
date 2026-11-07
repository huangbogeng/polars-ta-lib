//! `polars_ta_lib._internal`: the plugin binary and the metadata bridge.

mod engine;
mod expressions;
mod meta;

use pyo3::prelude::*;

/// Every TA-Lib function's Python-facing metadata, as JSON.
#[pyfunction]
fn functions_json() -> String {
    meta::functions_json()
}

#[pymodule]
fn _internal(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(functions_json, m)?)?;
    Ok(())
}
