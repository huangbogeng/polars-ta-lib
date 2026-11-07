//! Metadata bridge and P1 naming rules.
//!
//! This is the single place that translates TA-Lib's names (`optInTimePeriod`,
//! `outMACDSignal`, …) into the Python-facing names used by both generated Python
//! code and the Rust output assembly.

use polars::prelude::{DataType, Field, PlSmallStr, PolarsError, PolarsResult};
use serde::Serialize;
use ta_lib::abstract_api::{
    self, FuncId, FuncInfo, InputInfo, InputType, OptInputType, OutputType,
};

use crate::engine::PRICE_COMPONENTS;

/// Find a TA-Lib function by name (case-insensitive).
pub(crate) fn find_func(name: &str) -> PolarsResult<FuncId> {
    abstract_api::get_func_handle(name).ok_or_else(|| {
        PolarsError::ComputeError(format!("unknown TA-Lib function `{name}`").into())
    })
}

/// `optInTimePeriod` -> `time_period`, `inReal0` -> `real0`.
pub(crate) fn param_python_name(raw: &str) -> String {
    snake_case(raw.strip_prefix("optIn").unwrap_or(raw))
}

/// `inReal` -> `real`, `inPeriods` -> `periods`, `inReal0` -> `real0`.
pub(crate) fn input_python_name(raw: &str) -> String {
    snake_case(raw.strip_prefix("in").unwrap_or(raw))
}

/// `outMACDSignal` -> `macd_signal`, `outRealUpperBand` -> `upper_band`.
pub(crate) fn output_field_name(raw: &str) -> String {
    let stripped = raw.strip_prefix("out").unwrap_or(raw);
    let stripped = match stripped.strip_prefix("Real") {
        Some(rest) if !rest.is_empty() => rest,
        _ => stripped,
    };
    let name = snake_case(stripped);
    if name.is_empty() {
        "value".to_string()
    } else {
        name
    }
}

/// Rust-side dtype for one output slot.
pub(crate) fn single_dtype(kind: OutputType) -> DataType {
    match kind {
        OutputType::Real => DataType::Float64,
        OutputType::Integer => DataType::Int32,
    }
}

/// Output dtype of a whole function: scalar dtype or a Struct of all outputs.
pub(crate) fn output_dtype(info: &FuncInfo) -> DataType {
    match info.outputs {
        [single] => single_dtype(single.kind),
        many => DataType::Struct(
            many.iter()
                .map(|output| {
                    Field::new(
                        PlSmallStr::from_string(output_field_name(output.param_name)),
                        single_dtype(output.kind),
                    )
                })
                .collect(),
        ),
    }
}

/// Expanded input names in TA-Lib declaration order.
pub(crate) fn flat_input_names(info: &FuncInfo) -> Vec<String> {
    let mut names = Vec::new();
    for input in info.inputs {
        match input.kind {
            InputType::Price => {
                for (bit, component) in PRICE_COMPONENTS.iter().enumerate() {
                    if input.flags.0 & (1 << bit) != 0 {
                        names.push((*component).to_string());
                    }
                }
            }
            _ => names.push(input_python_name(input.param_name)),
        }
    }
    names
}

/// C2 default column for a Real input, or `None` when the caller must supply it.
fn input_default(input: &InputInfo) -> Option<&'static str> {
    match input.kind {
        InputType::Real => match input.param_name {
            "inReal" => Some("close"),
            "inPeriods" => Some("periods"),
            _ => None,
        },
        _ => None,
    }
}

/// Convert `CamelCase`, `UPPERCase` and `FastK_Period` to snake_case.
pub(crate) fn snake_case(input: &str) -> String {
    let chars: Vec<char> = input.chars().collect();
    let mut out = String::with_capacity(input.len() + 4);

    for (index, &ch) in chars.iter().enumerate() {
        if ch == '_' || ch == '-' || ch == ' ' {
            if !out.is_empty() && !out.ends_with('_') {
                out.push('_');
            }
            continue;
        }

        if ch.is_ascii_uppercase() {
            let previous = index.checked_sub(1).map(|i| chars[i]);
            let next = chars.get(index + 1).copied();
            let boundary = !out.is_empty()
                && !out.ends_with('_')
                && (previous.is_some_and(|p| p.is_ascii_lowercase() || p.is_ascii_digit())
                    || (previous.is_some_and(|p| p.is_ascii_uppercase())
                        && next.is_some_and(|n| n.is_ascii_lowercase())));
            if boundary {
                out.push('_');
            }
            out.push(ch.to_ascii_lowercase());
        } else {
            out.push(ch.to_ascii_lowercase());
        }
    }

    out
}

/// Metadata exposed to Python as JSON.
pub(crate) fn functions_json() -> String {
    let functions: Vec<FunctionMeta> = abstract_api::FUNCS.iter().map(function_meta).collect();
    serde_json::to_string(&functions).expect("TA-Lib metadata is JSON-serializable")
}

#[derive(Serialize)]
struct FunctionMeta {
    name: &'static str,
    python_name: String,
    group: &'static str,
    hint: &'static str,
    inputs: Vec<InputMeta>,
    params: Vec<ParamMeta>,
    outputs: Vec<OutputMeta>,
}

#[derive(Serialize)]
struct InputMeta {
    kind: &'static str,
    raw_name: &'static str,
    py_name: Option<String>,
    default: Option<String>,
    components: Vec<ComponentMeta>,
}

#[derive(Serialize)]
struct ComponentMeta {
    name: &'static str,
    default: &'static str,
}

#[derive(Serialize)]
struct ParamMeta {
    raw_name: &'static str,
    py_name: String,
    display_name: &'static str,
    hint: &'static str,
    kind: &'static str,
    min: Option<f64>,
    max: Option<f64>,
    default: f64,
    suggested: Option<[f64; 3]>,
    values: Option<Vec<(f64, &'static str)>>,
}

#[derive(Serialize)]
struct OutputMeta {
    raw_name: &'static str,
    field: String,
    dtype: &'static str,
}

fn function_meta(info: &FuncInfo) -> FunctionMeta {
    FunctionMeta {
        name: info.name,
        python_name: info.name.to_ascii_lowercase(),
        group: info.group.as_str(),
        hint: info.hint,
        inputs: info.inputs.iter().map(input_meta).collect(),
        params: info.opt_inputs.iter().map(param_meta).collect(),
        outputs: info
            .outputs
            .iter()
            .map(|output| OutputMeta {
                raw_name: output.param_name,
                field: output_field_name(output.param_name),
                dtype: match output.kind {
                    OutputType::Real => "float64",
                    OutputType::Integer => "int32",
                },
            })
            .collect(),
    }
}

fn input_meta(input: &InputInfo) -> InputMeta {
    match input.kind {
        InputType::Price => InputMeta {
            kind: "price",
            raw_name: input.param_name,
            py_name: None,
            default: None,
            components: PRICE_COMPONENTS
                .iter()
                .enumerate()
                .filter(|(bit, _)| input.flags.0 & (1 << bit) != 0)
                .map(|(_, name)| ComponentMeta {
                    name,
                    default: name,
                })
                .collect(),
        },
        InputType::Real => InputMeta {
            kind: "real",
            raw_name: input.param_name,
            py_name: Some(input_python_name(input.param_name)),
            default: input_default(input).map(str::to_string),
            components: Vec::new(),
        },
        InputType::Integer => InputMeta {
            kind: "integer",
            raw_name: input.param_name,
            py_name: Some(input_python_name(input.param_name)),
            default: None,
            components: Vec::new(),
        },
    }
}

fn param_meta(param: &ta_lib::abstract_api::OptInputInfo) -> ParamMeta {
    let mut meta = ParamMeta {
        raw_name: param.param_name,
        py_name: param_python_name(param.param_name),
        display_name: param.display_name,
        hint: param.hint,
        kind: "",
        min: None,
        max: None,
        default: 0.0,
        suggested: None,
        values: None,
    };

    match param.kind {
        OptInputType::IntegerRange {
            min,
            max,
            default,
            suggested,
            ..
        } => {
            meta.kind = "int_range";
            meta.min = Some(min as f64);
            meta.max = Some(max as f64);
            meta.default = default as f64;
            meta.suggested = Some([suggested.0 as f64, suggested.1 as f64, suggested.2 as f64]);
        }
        OptInputType::RealRange {
            min,
            max,
            default,
            suggested,
            ..
        } => {
            meta.kind = "real_range";
            meta.min = Some(min);
            meta.max = Some(max);
            meta.default = default;
            meta.suggested = Some([suggested.0, suggested.1, suggested.2]);
        }
        OptInputType::IntegerList { values, default } => {
            meta.kind = "int_list";
            meta.default = default as f64;
            meta.values = Some(
                values
                    .iter()
                    .map(|(value, display)| (*value as f64, *display))
                    .collect(),
            );
        }
        OptInputType::RealList { values, default } => {
            meta.kind = "real_list";
            meta.default = default;
            meta.values = Some(values.to_vec());
        }
    }

    meta
}
