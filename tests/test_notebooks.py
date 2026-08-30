"""Notebook smoke tests — every shipped marimo app must run headlessly.

Execution is forced offline via ``SABERKIT_OFFLINE=1`` so the notebooks fall
back to committed fixtures and CI never touches the network. A cell that
raises fails the test through ``app.run()``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

marimo = pytest.importorskip("marimo")
pytest.importorskip("altair")

NOTEBOOKS = ["percentile_explorer", "pitcher_explorer", "saberkit_tour"]


def _load(name: str) -> Any:
    path = Path(__file__).resolve().parent.parent / "notebooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"saberkit_nb_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_notebook_runs_headless_and_produces_tables(
    name: str, monkeypatch
) -> None:
    monkeypatch.setenv("SABERKIT_OFFLINE", "1")

    module = _load(name)
    _, defs = module.app.run()

    table = defs["table"]
    assert table.height > 0, "the compute cell produced no rows"
    assert any(col.endswith("_pct") for col in table.columns), (
        "percentile columns missing from the notebook's table"
    )


def test_pitcher_explorer_exposes_minus_family(monkeypatch) -> None:
    monkeypatch.setenv("SABERKIT_OFFLINE", "1")

    module = _load("pitcher_explorer")
    _, defs = module.app.run()

    table = defs["table"]
    assert "era_minus" in table.columns
    assert "fip_minus" in table.columns
