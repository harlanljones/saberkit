"""Fast batch sabermetrics, backed by Rust.

``saberkit`` computes the "plus" family of baseball statistics (OPS+, sOPS+,
ERA+, wRC+), the FanGraphs "minus" family, and Baseball-Savant-style league
percentile rankings.

Every statistic accepts either plain numbers or Arrow arrays. Pass a
``polars.Series``, a ``pyarrow.Array``, or a pandas ``ArrowDtype`` column and it
crosses into Rust with no copy; pass floats and you get a float back.

    >>> import saberkit
    >>> round(saberkit.obp(h=150, bb=60, hbp=5, ab=500, sf=5), 4)
    0.3772
"""

from __future__ import annotations

from typing import Any

from . import _core
from ._core import SaberError

__all__ = ["SaberError", "obp", "slg", "__version__"]

__version__: str = _core.__version__


def _is_arrow(obj: Any) -> bool:
    """Report whether ``obj`` can cross the boundary as an Arrow array.

    Anything implementing the Arrow PyCapsule interface qualifies, which covers
    polars, pyarrow, pandas ArrowDtype columns, and nanoarrow.
    """
    return hasattr(obj, "__arrow_c_array__") or hasattr(obj, "__arrow_c_stream__")


def obp(h: Any, bb: Any, hbp: Any, ab: Any, sf: Any) -> Any:
    """On-base percentage: ``(H + BB + HBP) / (AB + BB + HBP + SF)``.

    Sacrifice bunts and catcher's interference are excluded from the
    denominator, per the standard definition.

    Returns ``None`` (or a null element) where the denominator is zero.
    """
    fn = _core.obp_batch if _is_arrow(h) else _core.obp
    return fn(h, bb, hbp, ab, sf)


def slg(h: Any, doubles: Any, triples: Any, hr: Any, ab: Any) -> Any:
    """Slugging percentage: total bases per at-bat.

    ``h`` is *total* hits; singles are derived as ``h - doubles - triples - hr``.

    Returns ``None`` (or a null element) where at-bats are zero.
    """
    fn = _core.slg_batch if _is_arrow(h) else _core.slg
    return fn(h, doubles, triples, hr, ab)
