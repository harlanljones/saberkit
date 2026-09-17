"""Generate the synthetic OpenBiomechanics test fixtures.

Every value written to the four CSVs in this directory is produced by this
script from a fixed seed. No value is taken from, or derived from, the
OpenBiomechanics Project data; only the column names and file shapes follow
upstream's schema. The value ranges below are literals justified by general
baseball knowledge, not by upstream statistics.

Runs offline: stdlib only, no network, no OBP file is ever opened.

Usage: python generate.py   (idempotent — same seed, byte-identical output)
"""

import csv
import random
from pathlib import Path

SEED = 20260915
HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Value ranges. Each range is a rough envelope from general baseball knowledge
# for amateur-through-professional athletes, chosen to be wide enough that the
# synthetic population looks plausible; nothing here reflects an upstream
# measurement or statistic.
# ---------------------------------------------------------------------------

PITCH_RANGES = {
    # Fastball-equivalent pitch speed: ~70 mph (young high school) to
    # ~95 mph (professional).
    "pitch_speed_mph": (70.0, 95.0),
    # Shoulder internal rotation is the fastest joint motion in the throw,
    # commonly quoted in the thousands of deg/s.
    "max_shoulder_internal_rotational_velo": (2500.0, 6500.0),
    # Elbow extension is much slower than shoulder IR but still fast.
    "max_elbow_extension_velo": (1000.0, 2500.0),
    # Trunk rotation, several hundred deg/s.
    "max_torso_rotational_velo": (350.0, 900.0),
    # Pelvis rotation leads the trunk, slightly slower than torso.
    "max_pelvis_rotational_velo": (300.0, 800.0),
    # Lead-knee extension during landing/block, a few hundred deg/s.
    "lead_knee_extension_angular_velo_max": (200.0, 800.0),
    # Center-of-mass speed toward the plate, human sprint-ish scale.
    "max_cog_velo_x": (1.5, 4.5),
    # Elbow varus moment: tens of Nm for amateurs, ~100 Nm for pros.
    "elbow_varus_moment": (30.0, 120.0),
    # Shoulder internal rotation moment: same order as elbow varus.
    "shoulder_internal_rotation_moment": (40.0, 110.0),
}

HIT_RANGES = {
    # Batted-ball exit velocity: ~60 mph (weak contact) to ~110 mph (elite).
    "exit_velo_mph_x": (60.0, 110.0),
    # Bat speed at contact: roughly half of exit velocity, 45–85 mph.
    "bat_speed_mph_max_x": (45.0, 85.0),
    # Swing kinematic sequence peaks, a few hundred to ~1000 deg/s.
    "pelvis_angular_velocity_seq_max_x": (400.0, 900.0),
    "torso_angular_velocity_seq_max_x": (500.0, 1100.0),
    "upper_arm_speed_mag_seq_max_x": (600.0, 1400.0),
    # Center-of-mass speed during the swing.
    "max_cog_velo_x": (1.5, 5.0),
}

PITCHING_COLUMNS = ["session_pitch", "session", "p_throws", *PITCH_RANGES]
PITCHING_METADATA_COLUMNS = ["session_pitch", "playing_level"]
HITTING_COLUMNS = ["session_swing", "session", *HIT_RANGES]
HITTING_METADATA_COLUMNS = [
    "session_swing",
    "user",
    "session",
    "highest_playing_level",
    "hitter_side",
]

PITCH_LEVELS = ["college", "high_school", "independent"]
HIT_LEVELS = ["college", "high_school"]


def fmt(value: float) -> str:
    """One decimal place keeps the CSVs small and stable."""
    return f"{value:.1f}"


def athlete_rows(
    rng: random.Random,
    *,
    n_athletes: int,
    base_session: int,
    trial_key: str,
    ranges: dict,
    null_column: str | None = None,
    null_athlete: int | None = None,
) -> list[dict[str, str]]:
    """Build per-trial dicts for a synthetic population.

    Each athlete gets 2-5 trials of metric values drawn independently from
    the ranges above. When `null_column`/`null_athlete` are given, the last
    trial of that athlete has that column nulled, so the notebook's null
    handling is exercised by a deliberate, deterministic fixture rather
    than by a draw of the RNG.
    """
    rows = []
    for a in range(n_athletes):
        session = base_session + a
        n_trials = rng.randint(2, 5)
        for t in range(1, n_trials + 1):
            row = {
                trial_key: f"{session}_{t}",
                "session": str(session),
            }
            for col, (lo, hi) in ranges.items():
                row[col] = fmt(rng.uniform(lo, hi))
            rows.append(row)
        # Deliberate single null, if configured for this call.
        if null_column is not None and null_athlete == a:
            rows[-1][null_column] = ""
    return rows


def generate() -> None:
    rng = random.Random(SEED)

    # --- Pitching -----------------------------------------------------
    # Sessions start at 900001: a reserved synthetic range above the id
    # space in use at the OBP pin. Fixture rows are only ever loaded in
    # place of upstream data, so the range is a readability convention.
    pitch_rows = athlete_rows(
        rng,
        n_athletes=12,
        base_session=900001,
        trial_key="session_pitch",
        ranges=PITCH_RANGES,
        # A deliberate null in one trial of one athlete.
        null_column="pitch_speed_mph",
        null_athlete=5,
    )
    # Assign levels and throwing hands per athlete (one session each).
    pitch_meta = []
    seen: dict[str, tuple[str, str]] = {}
    for row in pitch_rows:
        if row["session"] not in seen:
            seen[row["session"]] = (
                rng.choice(PITCH_LEVELS),
                rng.choice(["R", "L"]),
            )
        level, throws = seen[row["session"]]
        row["p_throws"] = throws
        pitch_meta.append(
            {"session_pitch": row["session_pitch"], "playing_level": level}
        )

    # --- Hitting --------------------------------------------------------
    # Sessions start at 99001 (five digits): above the hitting id space at
    # the pin, yet small enough that the metadata copy's six-character
    # zero-padding is exercised ("099001") while POI stays unpadded.
    hit_rows = athlete_rows(
        rng,
        n_athletes=12,
        base_session=99001,
        trial_key="session_swing",
        ranges=HIT_RANGES,
        # A deliberate null in one trial of one athlete (not the all-null
        # exit-velocity hitter below).
        null_column="bat_speed_mph_max_x",
        null_athlete=3,
    )
    # One hitter whose exit_velo_mph_x is null in every trial (a distinct
    # athlete from the deliberate single-null above keeps the two null
    # paths of the notebook separate).
    all_null_hitter = hit_rows[len(hit_rows) // 2]["session"]
    for row in hit_rows:
        if row["session"] == all_null_hitter:
            row["exit_velo_mph_x"] = ""
    hit_meta = []
    seen = {}
    for row in hit_rows:
        if row["session"] not in seen:
            seen[row["session"]] = (
                rng.choice(HIT_LEVELS),
                rng.choice(["R", "L"]),
            )
        level, side = seen[row["session"]]
        row["hitter_side"] = side
        # Metadata-only user/session are zero-padded to six characters;
        # the join key session_swing stays unpadded in both tables.
        hit_meta.append(
            {
                "session_swing": row["session_swing"],
                "user": row["session"].zfill(6),
                "session": row["session"].zfill(6),
                "highest_playing_level": level,
                "hitter_side": side,
            }
        )

    write_csv("pitching_poi.csv", PITCHING_COLUMNS, pitch_rows)
    write_csv("pitching_metadata.csv", PITCHING_METADATA_COLUMNS, pitch_meta)
    write_csv("hitting_poi.csv", HITTING_COLUMNS, hit_rows)
    write_csv("hitting_metadata.csv", HITTING_METADATA_COLUMNS, hit_meta)


def write_csv(name: str, columns: list[str], rows: list[dict]) -> None:
    with (HERE / name).open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=columns, lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    generate()
