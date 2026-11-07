# 实施计划

依据 `ARCHITECTURE.md`。每个阶段都有可验证的产物；未通过验收标准不进入下一阶段。

## 0. 当前状态

- 设计决策：D1–D10 已定（见 `ARCHITECTURE.md` 第 2 节）。
- 代码：未开始。
- 环境：Rust 1.95（Polars 依赖的 `sysinfo 0.39` 要求 1.95）、Python 3.11/3.12、Polars 2.1.0、`ta-lib 0.8.3` 可编译。

## 1. 实现状态（2026-11-07）

- M0 文档：完成。
- M1 骨架：完成；`maturin develop --uv` 成功。
- M2 引擎：完成；引擎行为由 Python 对照测试覆盖（`extension-module` 下 `cargo test` 无法链接 Python 符号，因此不设 Rust 测试目标）。
- M3 插件边界：完成；N1、Struct、Int32、空/短序列、多 chunk 均验收。
- M4 Python API：完成；237 个顶层函数、签名、docstring、`.pyi`、`FUNCS`。
- M5 测试：24 个 pytest 通过；237 函数与 `polars-talib-fast==2.0.0` 在稠密有限数据上数值一致；参数、分组、边界、错误路径已覆盖。兼容性已验证：Polars 2.1.0 / Python 3.11、Polars 2.1.0 / Python 3.12。性能 smoke（dev build，1M 行）：SMA 28.7 ms、EMA 19.9 ms、RSI 21.6 ms、ATR 54.8 ms、MACD 27.3 ms（非硬阈值）。
- M6 打包：README、LICENSE、NOTICE、CI 工作流已加入；包名统一为 `polars_ta_lib`（PyPI 未占用；`polars_ta` import 与已有 `polars-ta` 冲突已消除）；release wheel 为 `cp311-abi3`（Python 3.11+，Polars 2.1+），已在 Python 3.11/3.12 + Polars 2.1.0 下验证（24 tests 通过）；MkDocs 文档已生成并通过 `mkdocs build --strict`；CI 已通过：Linux push/PR，macOS/Windows tag/manual。

## 2. 里程碑

> 完成状态以第 1 节为准；下列 checkbox 是原始任务清单，部分细项已由其他条目覆盖或后置。

### M0 文档

- [x] `ARCHITECTURE.md`
- [x] `PLAN.md`
- [ ] 对照 D1–D10 逐项复核，确认没有遗留矛盾

**验收**：文档中的 API、命名、缺失值、范围与讨论结论一致。

### M1 项目骨架

任务：

- [ ] `Cargo.toml`
  - `cdylib`，lib name `polars_ta_lib`
  - `pyo3 0.29`（`extension-module`、`abi3-py311`）
  - `pyo3-polars 0.28`（`derive`、`dtype-struct`）
  - `polars 0.55.2`（`default-features=false`、`dtype-struct`）
  - `polars-arrow 0.55.2`
  - `serde`、`serde_json`
  - `ta-lib = "=0.8.3"`
- [ ] `pyproject.toml`
  - maturin backend
  - `module-name = "polars_ta_lib._internal"`
  - `python-source = "python"`
  - `requires-python = ">=3.11"`
  - `dependencies = ["polars>=2.1,<3"]`
- [ ] 目录：`src/`、`python/polars_ta_lib/`、`tests/`
- [ ] `src/lib.rs`
  - `#[pymodule] _internal`
  - `__version__`
  - 系统 allocator（Arrow release callback 负责释放 buffer）
  - `functions_json()` 导出元数据
- [ ] `python/polars_ta_lib/__init__.py`（先只导出 `__version__`）
- [ ] `.gitignore`

**验收**：

- `maturin develop` 成功。
- `python -c "import polars_ta_lib; print(polars_ta_lib.__version__)"` 成功。
- 安装后的包目录包含扩展 `.so`，`Path(__file__).parent` 可被 `register_plugin_function` 解析。

### M2 TA-Lib 引擎层

任务：

- [ ] `src/meta.rs`
  - `FuncMeta`、`InputMeta`、`ParamMeta`、`OutputMeta` 序列化结构
  - `input_py_name`、`param_py_name`、`field_name`、`snake_case`
  - `output_spec(FuncInfo) -> DataType`
  - `find_func(name) -> PolarsResult<FuncId>`
  - 命名映射、237 函数元数据完整性、输出字段唯一性由 Python 测试覆盖
- [ ] `src/engine.rs`
  - `Function` 表（`OnceLock` 或直接使用 `FuncInfo`）
  - 输入宽度/绑定顺序
  - 参数绑定（Int/Float、范围/类型校验）
  - `lookback()`、输出缓冲分配、`call(0, n-1)`
  - `OutRange` 校验
  - 错误映射：`RetCode` → 带函数名/参数值的错误
  - 短序列/空序列路径；参数验证在 `n == 0` / 短序列时仍执行
  - 引擎行为通过 Python 对照测试覆盖（SMA/EMA/ATR/MACD、Int32、位置输出、多 Real、非法参数、短序列）

**验收**：

- `cargo check` 通过；引擎行为由 Python 测试覆盖。
- 引擎层不 import `polars`。
- 对已知输入，SMA/EMA 前几个值与手算一致；MACD 3 个输出的 lookback 一致。

### M3 Polars 插件边界

任务：

- [ ] `src/expressions.rs`
  - `CallKwargs { name, params: Vec<Number> }`
  - `#[polars_expr(output_type_func_with_kwargs = output_type)]`
  - `output_type`：单输出 `Float64`/`Int32`；多输出 `Struct`
  - 输入转换：
    - 稠密单 chunk `Float64` 零复制；
    - 其他 cast + 复制；
    - null/NaN/Inf 检查与错误消息；
    - 长度一致性检查；
  - 输出装配：
    - 前导 `lookback` 行 validity=false；
    - 单输出 `Series`；多输出 `StructChunked`；
    - 空/短序列全 null；
  - 不使用 `PolarsAllocator`（macOS 导入崩溃）
- [ ] `python/polars_ta_lib/__init__.py` 增加一个手动 `sma` 包装用于 smoke。

**验收**：

- `pta.sma(pl.col("close"), time_period=3)` 返回 `Float64`，前 2 行为 null。
- `pta.macd(pl.col("close"))` 返回 Struct，字段 `macd`/`macd_signal`/`macd_hist`。
- `pta.cdlengulfing(...)` 返回 `Int32`，前导为 null。
- 空 Series 返回空、dtype 正确。
- 长度 < lookback 返回全 null，不报错。
- 含 null/NaN/Inf 的输入报 `ComputeError`。
- 多 chunk 输入结果与单 chunk 一致。

### M4 Python API 生成

任务：

- [ ] `src/lib.rs` 的 `functions_json()` 输出完整元数据（见 `ARCHITECTURE.md` 第 9 节）。
- [ ] 仅生成顶层函数；不注册 `.ta` 命名空间；默认列严格按 C2 / 元数据 `default` 字段。
- [ ] `python/polars_ta_lib/_build.py`
  - `Spec`/`Param`/`Output` 数据类
  - `signature(spec)`：输入 + 参数；默认列直接取自元数据的 `default` 字段（多 Real 为 `None`）
  - `function(spec)`：绑定参数、构建 kwargs、调用 `register_plugin_function`
  - 参数校验：int/real 范围、list 值/显示名
  - `ma_type` 字符串映射
  - docstring 生成
  - `group`/`FUNCS`
- [ ] `python/polars_ta_lib/__init__.py`：导出 237 个函数 + `FUNCS`
- [ ] `python/polars_ta_lib/typing.py`
- [ ] `python/polars_ta_lib/_internal.pyi`
- [ ] `python/polars_ta_lib/py.typed`
- [ ] 生成式 `.pyi`（首版可先由测试校验签名，再提交生成文件）

**验收**：

- `len(pta.FUNCS) == 237`。
- 每个函数有 `inspect.signature`、`__doc__`。
- `pta.sma()` 默认为 `pl.col("close")`；`pta.atr()` 默认 high/low/close。
- `pta.beta(...)` 必须显式两个序列。
- `pta.ma(pl.col("close"), ma_type="sma")` 与整数 `0` 等价。
- 未知参数/越界参数抛 `TypeError`/`ValueError`（Python 侧）或 `ComputeError`（Rust 侧）。

### M5 测试与 fast 对照

任务：

- [ ] dev 依赖：`polars-talib-fast==2.0.0`、`pytest`、`numpy`
- [ ] `tests/conftest.py`：合成数据、归一化函数
- [ ] `tests/test_api.py`
  - 237 函数覆盖
  - 元数据与 `FUNCS`/签名一致
  - 输出字段名/顺序
- [ ] `tests/test_values.py`
  - 对每个函数：默认参数、短窗口
  - 与 fast 对照：dtype、长度、字段、数值
  - 分组 `.over("symbol")`
  - `ma_type` 字符串/整数
- [ ] `tests/test_edges.py`
  - 空输入、短输入
  - 多 chunk
  - `Int32`/`Float32` 输入
  - null/NaN/Inf 报错
  - 非法参数、未知函数
  - 长度不一致（如可构造）
- [x] 严格性测试已合并到 `tests/test_edges.py`：前导 null、Int32 前导 null、`MAXINDEX`/`MINMAXINDEX` 位置、错误消息包含列名/位置
- [x] 性能 smoke：1M 行 × 5 个指标，记录耗时（dev build，见状态节），不做硬阈值

**验收**：

- `pytest` 全绿。
- 237 函数全部有对照结果；差异仅为归一化后的 null/NaN 表达。
- N1 边界行为全部有测试。
- 分组结果与逐组单独计算一致。

### M6 打包与发布准备

任务：

- [x] `README.md`：安装、用法、默认列、N1 契约、示例、与 fast 的区别
- [x] `LICENSE`（MIT）+ `NOTICE`/`LICENSES/TA-Lib.txt`
- [x] `.github/workflows/ci.yml`
  - Linux/macOS/Windows
  - Rust fmt/clippy
  - maturin build/develop
  - pytest
- [x] `maturin build --release` 产出 abi3 wheel（manylinux_2_34_x86_64），并在全新 venv 中安装验证
- [x] 文档：`mkdocs.yml` + `tools/generate_docs.py`，237 函数 API reference，`mkdocs build --strict` 通过
- [x] 版本策略：`ta-lib` 精确 pin；`polars` 版本对写入 README

**验收**：

- 本地 wheel 可安装，`import polars_ta_lib` 正常。
- CI 三平台通过。
- `cargo clippy --all-targets` 无错误。

## 3. 测试矩阵

| 类别 | 代表函数 | 关注点 |
|---|---|---|
| 单 Real | `sma`, `ema`, `rsi`, `macd` | 默认 `close`、前导 null、递归指标 |
| Price HLC | `atr`, `adx`, `willr` | 输入展开顺序 high/low/close |
| Price OHLCV | `mfi`, `adosc`, `cmf` | 四/五列绑定 |
| Price OHLC | `cdl2crows`, `cdlengulfing` | Int32 输出、零参数 |
| 多 Real | `beta`, `correl`, `add`, `sub`, `mult` | 必须显式；无默认 |
| 多输出 | `macd`, `bbands`, `stoch`, `minmax` | Struct 字段/顺序 |
| 位置输出 | `maxindex`, `minindex`, `minmaxindex` | Int32 位置、无偏移 |
| 列表参数 | `ma`, `bbands`, `macdext` | `ma_type` 字符串/整数 |
| 实数参数 | `bbands`, `sar`, `alma` | 范围、精度 |
| 多参数 | `sarext`, `kstext`, `stoch` | 签名/默认值 |
| 短 lookback | `ht_dcperiod`, `ht_sine` | 短序列全 null |
| 多 Real + 参数 | `mavp` | `periods` 默认列、参数范围 |
| 单输入 + Volume | `obv`, `vwma` | Real + PriceV 默认 close/volume |

## 4. 验收标准（Definition of Done）

- `maturin develop` / `maturin build --release` 成功。
- `pytest` 全绿，覆盖 237 函数。
- 所有函数返回长度等于输入；dtype 与元数据一致。
- 前导 warm-up 区为 Polars null；Int32 不把 0 当缺失。
- 输入 null/NaN/Inf 报明确错误；空/短序列不报错。
- `.over()` 分组结果与逐组计算一致。
- `FUNCS`、函数签名、docstring、`.pyi` 一致。
- README 明确 N1 契约、默认列规则、与 fast/ta-lib-python 的差异。
- License/NOTICE 完整。

## 5. 常用命令

```bash
# 环境
uv venv .venv
uv pip install --python .venv/bin/python maturin pytest numpy 'polars>=2.1,<3' 'polars-talib-fast==2.0.0'

# 构建
source .venv/bin/activate
maturin develop

# Rust 检查
cargo check

# Python 测试
pytest -q

# 发布构建
maturin build --release
```

## 6. 风险与待确认项

- **P1 字段名映射**：需要生成 237 函数的字段清单并人工抽查多输出函数，防止重名。
- **函数名冲突**：`max`、`min`、`sum`、`add`、`sub` 等会遮蔽 Python 内置；文档建议 `import polars_ta_lib as pta`，不要 `from polars_ta_lib import *`。
- **单 Real 默认 `close` 的合理性**：`acos`/`ln`/`sqrt` 等数学函数默认 `close` 只是统一规则；如用户觉得别扭，后续可改为显式。
- **Int → Float64 精度**：超过 2^53 的整数会丢精度；文档说明，必要时报错。
- **fast 对照的版本漂移**：固定 `polars-talib-fast==2.0.0`；升级需重新评估归一化规则。
- **Polars 版本**：Rust 0.55.2 + Polars 2.1.x 为实测组合；`polars>=2.1,<3` 需在 CI 中覆盖。
- **性能**：N1 的有限性扫描是固定成本；若 1M 行场景明显变慢，再考虑分块/SIMD，但不改变契约。
- **复用 fast 代码的许可**：若直接改写 `talib.rs`，在 `NOTICE` 中保留 MIT 声明；测试只依赖其 wheel，不复制 golden 数据。
