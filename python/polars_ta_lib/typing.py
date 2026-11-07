from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import polars as pl

    IntoExprColumn = Union[pl.Expr, str, pl.Series]
