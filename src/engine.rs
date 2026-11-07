//! Safe layer over TA-Lib's abstract API.
//!
//! This module operates on plain `&[f64]` slices and deliberately does not import
//! Polars. It binds inputs/parameters, asks TA-Lib for the lookback, runs the
//! function, and returns full-length output buffers whose leading `lookback` rows
//! are placeholders for the caller to mark as null.

use std::fmt;
use std::sync::LazyLock;

use serde::Deserialize;
use ta_lib::abstract_api::{FuncInfo, InputType, OptInputType, OutputType, ParamHolder};
use ta_lib::{Core, RetCode};

/// Price components in the order `ParamHolder::set_price_input` takes them.
pub(crate) const PRICE_COMPONENTS: [&str; 6] =
    ["open", "high", "low", "close", "volume", "open_interest"];

/// One optional parameter value as supplied by Python.
#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(untagged)]
pub(crate) enum Number {
    Int(i64),
    Float(f64),
}

impl fmt::Display for Number {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Number::Int(v) => write!(f, "{v}"),
            Number::Float(v) => write!(f, "{v}"),
        }
    }
}

/// An error from the engine layer. The Polars boundary converts it to `ComputeError`.
#[derive(Debug, Clone)]
pub(crate) struct EngineError(pub String);

impl fmt::Display for EngineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for EngineError {}

/// One output column, full input length; rows before `lookback` are unused zeros.
pub(crate) enum Column {
    Real(Vec<f64>),
    Integer(Vec<i32>),
}

/// Result of one indicator call.
pub(crate) struct EngineOutput {
    pub lookback: usize,
    pub columns: Vec<Column>,
}

/// Number of input series a function consumes, with price bundles expanded.
pub(crate) fn input_width(info: &FuncInfo) -> usize {
    info.inputs
        .iter()
        .map(|input| match input.kind {
            InputType::Price => (input.flags.0 & 0x3F).count_ones() as usize,
            _ => 1,
        })
        .sum()
}

fn core() -> &'static Core {
    static CORE: LazyLock<Core> = LazyLock::new(Core::new);
    &CORE
}

/// Run one TA-Lib function.
///
/// `inputs` are the expanded series in TA-Lib declaration order; every slice must
/// have the same length. `params` are all optional parameters in declaration
/// order (defaults included).
pub(crate) fn run(
    info: &FuncInfo,
    inputs: &[&[f64]],
    params: &[Number],
) -> Result<EngineOutput, EngineError> {
    let width = input_width(info);
    if inputs.len() != width {
        return Err(EngineError(format!(
            "{}: expects {width} input series, got {}",
            info.name,
            inputs.len()
        )));
    }
    let n = inputs.first().map(|s| s.len()).unwrap_or(0);
    if let Some((index, series)) = inputs.iter().enumerate().find(|(_, s)| s.len() != n) {
        return Err(EngineError(format!(
            "{}: input series {index} has length {}, expected {n}",
            info.name,
            series.len()
        )));
    }

    let columns;
    let lookback;
    {
        let mut holder = info.id.new_call(core());
        bind_params(&mut holder, info, params)?;
        lookback = holder
            .lookback()
            .map_err(|code| code_error(info, params, code))?;

        // Parameter validation happened above. Empty and too-short inputs still
        // produce a correctly typed, all-null output without calling TA-Lib.
        if n == 0 || lookback >= n {
            return Ok(EngineOutput {
                lookback,
                columns: empty_columns(info, n),
            });
        }

        bind_inputs(&mut holder, info, inputs)?;
        let mut buffers = empty_columns(info, n);
        for (slot, (column, output)) in buffers.iter_mut().zip(info.outputs.iter()).enumerate() {
            match (column, output.kind) {
                (Column::Real(values), OutputType::Real) => {
                    holder
                        .set_output(slot, &mut values[lookback..])
                        .map_err(|code| {
                            EngineError(format!("{}: output {slot}: {code}", info.name))
                        })?;
                }
                (Column::Integer(values), OutputType::Integer) => {
                    holder
                        .set_int_output(slot, &mut values[lookback..])
                        .map_err(|code| {
                            EngineError(format!("{}: output {slot}: {code}", info.name))
                        })?;
                }
                _ => {
                    return Err(EngineError(format!(
                        "{}: output {slot} type mismatch",
                        info.name
                    )))
                }
            }
        }

        let range = holder
            .call(0, n - 1)
            .map_err(|code| code_error(info, params, code))?;
        if range.beg_idx != lookback || range.count != n - lookback {
            return Err(EngineError(format!(
                "{}: TA-Lib wrote rows {}..{}, expected {lookback}..{n}",
                info.name,
                range.beg_idx,
                range.beg_idx + range.count
            )));
        }

        // End the mutable borrows of `buffers` before moving it out.
        #[expect(clippy::drop_non_drop, reason = "ends the borrows of `buffers`")]
        drop(holder);
        columns = buffers;
    }

    Ok(EngineOutput { lookback, columns })
}

fn bind_params(
    holder: &mut ParamHolder<'_>,
    info: &FuncInfo,
    params: &[Number],
) -> Result<(), EngineError> {
    if params.len() != info.opt_inputs.len() {
        return Err(EngineError(format!(
            "{}: expects {} parameters, got {}",
            info.name,
            info.opt_inputs.len(),
            params.len()
        )));
    }

    for (index, (param, value)) in info.opt_inputs.iter().zip(params).enumerate() {
        match param.kind {
            OptInputType::IntegerRange { .. } | OptInputType::IntegerList { .. } => {
                let value = value.as_i32(info, param.param_name)?;
                holder.set_opt_input(index, value).map_err(|code| {
                    EngineError(format!(
                        "{}: {}={value}: {code}",
                        info.name, param.param_name
                    ))
                })?;
            }
            OptInputType::RealRange { .. } | OptInputType::RealList { .. } => {
                let value = value.as_f64(info, param.param_name)?;
                holder.set_opt_input(index, value).map_err(|code| {
                    EngineError(format!(
                        "{}: {}={value}: {code}",
                        info.name, param.param_name
                    ))
                })?;
            }
        }
    }
    Ok(())
}

fn bind_inputs<'a>(
    holder: &mut ParamHolder<'a>,
    info: &FuncInfo,
    inputs: &[&'a [f64]],
) -> Result<(), EngineError> {
    let mut cursor = 0;

    for (slot, input) in info.inputs.iter().enumerate() {
        match input.kind {
            InputType::Real => {
                let series = *inputs
                    .get(cursor)
                    .ok_or_else(|| EngineError(format!("{}: missing input {slot}", info.name)))?;
                holder
                    .set_input(slot, series)
                    .map_err(|code| EngineError(format!("{}: input {slot}: {code}", info.name)))?;
                cursor += 1;
            }
            InputType::Integer => {
                return Err(EngineError(format!(
                    "{}: integer inputs are not supported",
                    info.name
                )));
            }
            InputType::Price => {
                let mut components: [Option<&[f64]>; 6] = [None; 6];
                for (bit, _component) in PRICE_COMPONENTS.iter().enumerate() {
                    if input.flags.0 & (1 << bit) != 0 {
                        let series = inputs.get(cursor).ok_or_else(|| {
                            EngineError(format!("{}: missing price component {bit}", info.name))
                        })?;
                        components[bit] = Some(*series);
                        cursor += 1;
                    }
                }
                let [open, high, low, close, volume, open_interest] = components;
                holder
                    .set_price_input(slot, open, high, low, close, volume, open_interest)
                    .map_err(|code| EngineError(format!("{}: input {slot}: {code}", info.name)))?;
            }
        }
    }

    if cursor != inputs.len() {
        return Err(EngineError(format!(
            "{}: {} unused input series",
            info.name,
            inputs.len() - cursor
        )));
    }
    Ok(())
}

fn empty_columns(info: &FuncInfo, n: usize) -> Vec<Column> {
    info.outputs
        .iter()
        .map(|output| match output.kind {
            OutputType::Real => Column::Real(vec![0.0; n]),
            OutputType::Integer => Column::Integer(vec![0; n]),
        })
        .collect()
}

fn code_error(info: &FuncInfo, params: &[Number], code: RetCode) -> EngineError {
    let values = info
        .opt_inputs
        .iter()
        .zip(params)
        .map(|(param, value)| format!("{}={value}", param.param_name))
        .collect::<Vec<_>>()
        .join(", ");
    if values.is_empty() {
        EngineError(format!("{}: {code} ({code:?})", info.name))
    } else {
        EngineError(format!("{}: {values}: {code} ({code:?})", info.name))
    }
}

impl Number {
    fn as_i32(self, info: &FuncInfo, name: &str) -> Result<i32, EngineError> {
        match self {
            Number::Int(value) => i32::try_from(value).map_err(|_| {
                EngineError(format!(
                    "{}: {name}={value} does not fit a 32-bit integer",
                    info.name
                ))
            }),
            Number::Float(value) => {
                if !value.is_finite() || value.fract() != 0.0 {
                    return Err(EngineError(format!(
                        "{}: {name}={value} must be an integer",
                        info.name
                    )));
                }
                if value < i32::MIN as f64 || value > i32::MAX as f64 {
                    return Err(EngineError(format!(
                        "{}: {name}={value} does not fit a 32-bit integer",
                        info.name
                    )));
                }
                Ok(value as i32)
            }
        }
    }

    fn as_f64(self, info: &FuncInfo, name: &str) -> Result<f64, EngineError> {
        let value = match self {
            Number::Int(value) => value as f64,
            Number::Float(value) => value,
        };
        if !value.is_finite() {
            return Err(EngineError(format!(
                "{}: {name}={value} must be finite",
                info.name
            )));
        }
        Ok(value)
    }
}
