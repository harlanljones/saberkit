"""Unit and smoke tests for the biomech explorer notebook.

The notebook fetches OpenBiomechanics data at runtime, so every test either
calls the ``@app.function`` helpers directly against the synthetic fixtures in
``tests/fixtures/openbiomechanics/`` (generated, never observed values) or
forces the headless offline run via ``SABERKIT_OFFLINE=1``. No test touches
the network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import polars as pl
import pytest

marimo = pytest.importorskip("marimo")
pytest.importorskip("altair")

FIXTURES = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "openbiomechanics"
)


def _load(name: str) -> Any:
    path = Path(__file__).resolve().parent.parent / "notebooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"saberkit_nb_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_bytes(key: str) -> bytes:
    return (FIXTURES / f"{key}.csv").read_bytes()


def _fixture_header(key: str) -> list[str]:
    text = _fixture_bytes(key).decode("utf-8")
    return text.splitlines()[0].split(",")


# Only the columns the notebook actually reads, transcribed from the headers
# at the pinned commit. The pin-bump procedure in docs/openbiomechanics.md
# re-verifies this literal against the live upstream headers.
UPSTREAM_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "pitching_metadata": [
        "session_pitch",
        "playing_level",
    ],
    "pitching_poi": [
        "session_pitch",
        "session",
        "p_throws",
        "pitch_speed_mph",
        "max_shoulder_internal_rotational_velo",
        "max_elbow_extension_velo",
        "max_torso_rotational_velo",
        "max_pelvis_rotational_velo",
        "lead_knee_extension_angular_velo_max",
        "max_cog_velo_x",
        "elbow_varus_moment",
        "shoulder_internal_rotation_moment",
    ],
    "hitting_metadata": [
        "session_swing",
        "highest_playing_level",
        "hitter_side",
    ],
    "hitting_poi": [
        "session_swing",
        "session",
        "exit_velo_mph_x",
        "bat_speed_mph_max_x",
        "pelvis_angular_velocity_seq_max_x",
        "torso_angular_velocity_seq_max_x",
        "upper_arm_speed_mag_seq_max_x",
        "max_cog_velo_x",
    ],
}


# ---------------------------------------------------------------------------
# per_athlete
# ---------------------------------------------------------------------------


def _trials_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "athlete": ["a", "a", "b", "b", "c", "c"],
            "trial": ["a_1", "a_2", "b_1", "b_2", "c_1", "c_2"],
            "level": [
                "college",
                "college",
                "high_school",
                "high_school",
                "independent",
                "independent",
            ],
            "hand": ["R", "R", "L", "L", "R", "R"],
            "pitch_speed_mph": [90.0, None, 80.0, 84.0, None, None],
        },
        schema_overrides={"pitch_speed_mph": pl.Float64},
    )


def test_per_athlete_max_skips_nulls() -> None:
    module = _load("biomech_explorer")
    out = module.per_athlete(_trials_frame(), ["pitch_speed_mph"], "max").sort(
        "athlete"
    )

    assert out["athlete"].to_list() == ["a", "b", "c"]
    # Athlete a's null trial is skipped; athlete c's all-null trials stay null.
    assert out["pitch_speed_mph"].to_list() == [90.0, 84.0, None]
    # n_trials counts every trial row, including ones holding nulls.
    assert out["n_trials"].to_list() == [2, 2, 2]
    assert out["level"].to_list() == ["college", "high_school", "independent"]
    assert out["hand"].to_list() == ["R", "L", "R"]


def test_per_athlete_mean_skips_nulls() -> None:
    module = _load("biomech_explorer")
    out = module.per_athlete(_trials_frame(), ["pitch_speed_mph"], "mean").sort(
        "athlete"
    )

    # a: mean of [90.0] (null skipped); b: mean of [80.0, 84.0]; c: all null.
    assert out["pitch_speed_mph"].to_list() == [90.0, 82.0, None]
    assert out["n_trials"].to_list() == [2, 2, 2]


def test_per_athlete_rejects_unknown_reducer() -> None:
    module = _load("biomech_explorer")
    with pytest.raises(ValueError, match="how must be 'max' or 'mean'"):
        module.per_athlete(_trials_frame(), ["pitch_speed_mph"], "median")


# ---------------------------------------------------------------------------
# load_discipline
# ---------------------------------------------------------------------------


def test_load_discipline_pitching_one_row_per_trial() -> None:
    module = _load("biomech_explorer")
    df = module.load_discipline(
        "pitching",
        metadata_csv=_fixture_bytes("pitching_metadata"),
        poi_csv=_fixture_bytes("pitching_poi"),
    )
    poi = pl.read_csv(_fixture_bytes("pitching_poi"), infer_schema=False)

    assert df.height == poi.height
    # athlete is taken from the POI session column, keyed by the trial join.
    merged = df.join(
        poi.select(["session_pitch", "session"]),
        left_on="trial",
        right_on="session_pitch",
    )
    assert merged["athlete"].to_list() == merged["session"].to_list()
    metrics = list(module.METRICS["pitching"]["ranked"]) + list(
        module.METRICS["pitching"]["load"]
    )
    for metric in metrics:
        assert df.schema[metric] == pl.Float64


def test_load_discipline_hitting_keeps_unpadded_string_ids() -> None:
    module = _load("biomech_explorer")
    meta_bytes = _fixture_bytes("hitting_metadata")
    poi_bytes = _fixture_bytes("hitting_poi")

    # infer_schema=False is honoured: the zero-padded metadata copies of
    # user/session stay strings.
    meta = pl.read_csv(meta_bytes, infer_schema=False)
    assert meta.schema["user"] == pl.String
    assert meta.schema["session"] == pl.String
    assert all(value.startswith("0") for value in meta["user"].to_list())

    df = module.load_discipline("hitting", metadata_csv=meta_bytes, poi_csv=poi_bytes)
    assert df.schema["athlete"] == pl.String
    assert df.schema["trial"] == pl.String
    poi = pl.read_csv(poi_bytes, infer_schema=False)
    expected_trials = dict(
        zip(poi["session_swing"].to_list(), poi["session"].to_list())
    )
    for row in df.iter_rows(named=True):
        # No leading zero: the POI ids from the synthetic range stay unpadded.
        assert re.fullmatch(r"9\d{4,5}", row["athlete"]) is not None
        suffix = row["trial"].split("_", 1)[1]
        assert row["trial"] == f"{row['athlete']}_{int(suffix)}"
        assert expected_trials[row["trial"]] == row["athlete"]


def test_load_discipline_missing_required_column_raises() -> None:
    module = _load("biomech_explorer")
    poi = pl.read_csv(_fixture_bytes("pitching_poi"), infer_schema=False)
    buffer = io.BytesIO()
    poi.drop("pitch_speed_mph").write_csv(buffer)

    with pytest.raises(ValueError, match="pitch_speed_mph"):
        module.load_discipline(
            "pitching",
            metadata_csv=_fixture_bytes("pitching_metadata"),
            poi_csv=buffer.getvalue(),
        )


def test_load_discipline_orphan_poi_trial_raises() -> None:
    module = _load("biomech_explorer")
    meta = pl.read_csv(_fixture_bytes("pitching_metadata"), infer_schema=False)
    buffer = io.BytesIO()
    meta.slice(1).write_csv(buffer)

    with pytest.raises(ValueError, match="900001_1"):
        module.load_discipline(
            "pitching",
            metadata_csv=buffer.getvalue(),
            poi_csv=_fixture_bytes("pitching_poi"),
        )


def test_load_discipline_unknown_discipline_raises() -> None:
    module = _load("biomech_explorer")
    with pytest.raises(ValueError, match="unknown discipline"):
        module.load_discipline(
            "basketball",
            metadata_csv=_fixture_bytes("pitching_metadata"),
            poi_csv=_fixture_bytes("pitching_poi"),
        )


# ---------------------------------------------------------------------------
# fetch_csv
# ---------------------------------------------------------------------------


def test_fetch_csv_caches_first_fetch(monkeypatch, tmp_path) -> None:
    module = _load("biomech_explorer")
    payload = b"col\n1\n"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(module, "OBP_FILES", {"demo": ("some/path.csv", digest)})

    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        calls.append(url)
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    data = module.fetch_csv("demo", cache_dir=tmp_path)
    assert data == payload
    assert (tmp_path / "demo.csv").read_bytes() == payload

    calls.clear()
    data = module.fetch_csv("demo", cache_dir=tmp_path)
    assert data == payload
    assert calls == [], "the second fetch must be served from the cache"


def test_fetch_csv_digest_mismatch_raises_and_writes_nothing(
    monkeypatch, tmp_path
) -> None:
    module = _load("biomech_explorer")
    payload = b"col\n1\n"
    monkeypatch.setattr(
        module,
        "OBP_FILES",
        {"demo": ("some/path.csv", "0" * 64)},
    )

    def fake_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=module.OBP_COMMIT):
        module.fetch_csv("demo", cache_dir=tmp_path)
    assert list(tmp_path.iterdir()) == [], "a digest mismatch writes nothing"


def test_fetch_csv_corrupted_cache_is_refetched(monkeypatch, tmp_path) -> None:
    module = _load("biomech_explorer")
    payload = b"col\n1\n"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(module, "OBP_FILES", {"demo": ("some/path.csv", digest)})
    (tmp_path / "demo.csv").write_bytes(b"corrupted")

    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        calls.append(url)
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    data = module.fetch_csv("demo", cache_dir=tmp_path)
    assert data == payload
    assert len(calls) == 1, "the corrupted cache file is fetched again once"
    assert (tmp_path / "demo.csv").read_bytes() == payload


def test_fetch_csv_http_error_raises_runtime_error_naming_url(
    monkeypatch, tmp_path
) -> None:
    module = _load("biomech_explorer")
    monkeypatch.setattr(
        module,
        "OBP_FILES",
        {"demo": ("some/path.csv", "0" * 64)},
    )

    def fake_urlopen(url: str, timeout: float | None = None) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="some/path.csv"):
        module.fetch_csv("demo", cache_dir=tmp_path)


def test_fetch_csv_unknown_key_raises(tmp_path) -> None:
    module = _load("biomech_explorer")
    with pytest.raises(ValueError, match="unknown OpenBiomechanics file key"):
        module.fetch_csv("nope", cache_dir=tmp_path)


# ---------------------------------------------------------------------------
# rank_population
# ---------------------------------------------------------------------------


def _athletes_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "athlete": ["a", "b", "c", "d"],
            "level": ["college", "college", "high_school", "college"],
            "hand": ["R", "R", "L", "R"],
            "n_trials": [2, 2, 1, 3],
            "pitch_speed_mph": [95.0, 90.0, 85.0, None],
            "elbow_varus_moment": [100.0, 90.0, 80.0, 70.0],
        },
        schema_overrides={
            "pitch_speed_mph": pl.Float64,
            "elbow_varus_moment": pl.Float64,
        },
    )


def test_rank_population_pct_columns_are_ranked_only() -> None:
    module = _load("biomech_explorer")
    out = module.rank_population(_athletes_frame(), ["pitch_speed_mph"])

    pct_columns = {col for col in out.columns if col.endswith("_pct")}
    assert pct_columns == {"pitch_speed_mph_pct"}
    assert "elbow_varus_moment_pct" not in out.columns

    # The fastest athlete ranks highest; nulls stay null.
    best = out.sort("pitch_speed_mph_pct", descending=True, nulls_last=True)["athlete"][
        0
    ]
    assert best == "a"
    assert out["pitch_speed_mph_pct"].max() == out["pitch_speed_mph_pct"][0]
    assert out["pitch_speed_mph_pct"][3] is None


def test_rank_population_empty_frame_does_not_raise() -> None:
    module = _load("biomech_explorer")
    empty = _athletes_frame().head(0)
    out = module.rank_population(empty, ["pitch_speed_mph"])

    assert out.height == 0
    assert "pitch_speed_mph_pct" in out.columns
    assert out.schema["pitch_speed_mph_pct"] == pl.Float64


def test_rank_population_all_null_metric_gives_null_pct() -> None:
    module = _load("biomech_explorer")
    athletes = pl.DataFrame(
        {
            "athlete": ["a", "b"],
            "exit_velo_mph_x": [None, None],
        }
    )
    out = module.rank_population(athletes, ["exit_velo_mph_x"])

    assert out["exit_velo_mph_x_pct"].is_null().all()
    assert out.schema["exit_velo_mph_x_pct"] == pl.Float64


def test_rank_population_partial_null_metric_ranks_finite_subset() -> None:
    module = _load("biomech_explorer")
    athletes = pl.DataFrame(
        {
            "athlete": ["a", "b", "c"],
            "max_cog_velo_x": [4.0, None, 2.0],
        },
        schema_overrides={"max_cog_velo_x": pl.Float64},
    )
    out = module.rank_population(athletes, ["max_cog_velo_x"])

    # The all-null athlete keeps a null percentile; the finite ones are
    # ranked among each other (this exercises the is_not_nan guard).
    assert out["max_cog_velo_x_pct"][1] is None
    ranked = out.filter(pl.col("max_cog_velo_x_pct").is_not_null()).sort(
        "max_cog_velo_x_pct"
    )
    assert ranked["athlete"].to_list() == ["c", "a"]
    assert ranked["max_cog_velo_x_pct"].to_list() == [
        ranked["max_cog_velo_x_pct"].min(),
        ranked["max_cog_velo_x_pct"].max(),
    ]


# ---------------------------------------------------------------------------
# small_population_note
# ---------------------------------------------------------------------------


def test_small_population_note_boundaries() -> None:
    module = _load("biomech_explorer")

    # An empty population is not a small population (cell 6 shows its own
    # callout there), and the threshold itself is not below the threshold.
    assert module.small_population_note(0) is None
    assert module.small_population_note(19) is not None
    assert module.small_population_note(20) is None


# ---------------------------------------------------------------------------
# METRICS integrity
# ---------------------------------------------------------------------------


def test_metrics_ranked_and_load_are_disjoint() -> None:
    module = _load("biomech_explorer")
    for discipline, roles in module.METRICS.items():
        overlap = set(roles["ranked"]) & set(roles["load"])
        assert not overlap, f"{discipline}: ranked and load overlap: {overlap}"


def test_metrics_columns_exist_in_fixture_headers() -> None:
    module = _load("biomech_explorer")
    for discipline in ("pitching", "hitting"):
        header = set(_fixture_header(f"{discipline}_poi"))
        for column in (
            *module.METRICS[discipline]["ranked"],
            *module.METRICS[discipline]["load"],
        ):
            assert column in header, (
                f"{discipline}: metric {column!r} missing from the fixture header"
            )


def test_upstream_required_columns_literal_covers_everything_read() -> None:
    module = _load("biomech_explorer")
    for discipline, (
        trial_key,
        level_column,
        hand_column,
        hand_table,
    ) in module.DISCIPLINES.items():
        poi_table = f"{discipline}_poi"
        metadata_table = f"{discipline}_metadata"
        poi_columns = set(UPSTREAM_REQUIRED_COLUMNS[poi_table])
        metadata_columns = set(UPSTREAM_REQUIRED_COLUMNS[metadata_table])

        for column in (
            *module.METRICS[discipline]["ranked"],
            *module.METRICS[discipline]["load"],
        ):
            assert column in poi_columns
        assert trial_key in poi_columns
        assert trial_key in metadata_columns
        assert "session" in poi_columns
        assert level_column in metadata_columns
        if hand_table == "poi":
            assert hand_column in poi_columns
        else:
            assert hand_column in metadata_columns

        # The literal must also be satisfiable by the fixture files, so a
        # fixture that drifts from the recorded columns fails here.
        header = set(_fixture_header(poi_table))
        assert poi_columns <= header
        assert metadata_columns <= set(_fixture_header(metadata_table))


# ---------------------------------------------------------------------------
# License gate and offline run
# ---------------------------------------------------------------------------


def test_license_gate_blocks_fetch_without_acceptance(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SABERKIT_OFFLINE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    calls: list[str] = []

    def recording_urlopen(url: str, *args: object, **kwargs: object) -> None:
        calls.append(url)
        raise AssertionError("the license gate let a fetch through")

    monkeypatch.setattr(urllib.request, "urlopen", recording_urlopen)

    module = _load("biomech_explorer")
    _, defs = module.app.run()

    # mo.stop in the gate skips only cells that reference a variable it
    # defines, so a data cell that dropped its license_ok reference would
    # still define trials and fetch — assert both names.
    assert "trials" not in defs
    assert "table" not in defs
    assert calls == [], "no network call may happen before the gate is accepted"
    assert not (tmp_path / "saberkit").exists()


def test_offline_run_ranks_all_pitching_metrics(monkeypatch) -> None:
    monkeypatch.setenv("SABERKIT_OFFLINE", "1")

    module = _load("biomech_explorer")
    _, defs = module.app.run()

    table = defs["table"]
    assert table.height > 0
    for metric in module.METRICS["pitching"]["ranked"]:
        assert f"{metric}_pct" in table.columns, (
            f"offline run is missing the {metric}_pct percentile column"
        )
