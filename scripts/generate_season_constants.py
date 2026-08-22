#!/usr/bin/env python3
"""Generate bundled league constants from Retrosheet event files.

This is a development tool, not a runtime dependency. It reads the Chadwick
Bureau Retrosheet repository and invokes ``cwevent`` to obtain stable,
documented event fields. Raw Retrosheet data is never included in saberkit.

The information used here was obtained free of charge from and is copyrighted
by Retrosheet. Interested parties may contact Retrosheet at
https://www.retrosheet.org/.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


FIELDS = "0,2,3,4,8,9,26,27,28,34,35,36,37,38,39,40,58,59,60,61"
EVENT_WALK = 14
EVENT_INTENTIONAL_WALK = 15
EVENT_HBP = 16
EVENT_SINGLE = 20
EVENT_DOUBLE = 21
EVENT_TRIPLE = 22
EVENT_HOME_RUN = 23
WEIGHT_EVENTS = {
    "w_bb": EVENT_WALK,
    "w_hbp": EVENT_HBP,
    "w_1b": EVENT_SINGLE,
    "w_2b": EVENT_DOUBLE,
    "w_3b": EVENT_TRIPLE,
    "w_hr": EVENT_HOME_RUN,
}


@dataclass(frozen=True)
class Event:
    game_id: str
    inning: int
    batting_home: int
    outs_before: int
    first: bool
    second: bool
    third: bool
    event_code: int
    batter_event: bool
    at_bat: bool
    hit_value: int
    sacrifice_fly: bool
    outs_on_play: int
    destinations: tuple[int, int, int, int]

    @property
    def runs(self) -> int:
        return sum(destination >= 4 for destination in self.destinations)

    @property
    def earned_runs(self) -> int:
        return sum(destination == 4 for destination in self.destinations)

    @property
    def state(self) -> tuple[int, int]:
        bases = int(self.first) | (int(self.second) << 1) | (int(self.third) << 2)
        return self.outs_before, bases


def parse_event(row: dict[str, str]) -> Event:
    return Event(
        game_id=row["GAME_ID"],
        inning=int(row["INN_CT"]),
        batting_home=int(row["BAT_HOME_ID"]),
        outs_before=int(row["OUTS_CT"]),
        first=bool(row["BASE1_RUN_ID"]),
        second=bool(row["BASE2_RUN_ID"]),
        third=bool(row["BASE3_RUN_ID"]),
        event_code=int(row["EVENT_CD"]),
        batter_event=row["BAT_EVENT_FL"] == "T",
        at_bat=row["AB_FL"] == "T",
        hit_value=int(row["H_CD"]),
        sacrifice_fly=row["SF_FL"] == "T",
        outs_on_play=int(row["EVENT_OUTS_CT"]),
        destinations=tuple(
            int(row[name])
            for name in ("BAT_DEST_ID", "RUN1_DEST_ID", "RUN2_DEST_ID", "RUN3_DEST_ID")
        ),
    )


def regular_event_files(season_dir: Path, year: int) -> list[Path]:
    files = sorted(
        path
        for suffix in ("EVA", "EVN")
        for path in season_dir.glob(f"{year}???.{suffix}")
    )
    if len(files) < 20:
        raise ValueError(f"{year}: found only {len(files)} regular-season event files")
    return files


def read_events(cwevent: Path, season_dir: Path, year: int) -> Iterator[Event]:
    files = regular_event_files(season_dir, year)
    with tempfile.TemporaryDirectory(prefix=f"saberkit-{year}-") as temp:
        data_dir = Path(temp)
        team_file = season_dir / f"TEAM{year}"
        if not team_file.exists():
            raise ValueError(f"{year}: missing {team_file}")
        (data_dir / f"team{year}").symlink_to(team_file.resolve())

        command = [
            str(cwevent),
            "-n",
            "-Q",
            "-D",
            str(data_dir),
            "-y",
            str(year),
            "-f",
            FIELDS,
            *(str(path) for path in files),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("failed to capture cwevent output")
        for row in csv.DictReader(process.stdout):
            yield parse_event(row)
        stderr = process.stderr.read()
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"cwevent failed for {year}: {stderr.strip()}")


def group_half_innings(events: Iterable[Event]) -> Iterator[list[Event]]:
    current_key: tuple[str, int, int] | None = None
    current: list[Event] = []
    for event in events:
        key = (event.game_id, event.inning, event.batting_home)
        if current_key is not None and key != current_key:
            yield current
            current = []
        current_key = key
        current.append(event)
    if current:
        yield current


def source_digest(files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def derive_year(cwevent: Path, source_root: Path, year: int) -> dict[str, float | int | str]:
    season_dir = source_root / "seasons" / str(year)
    files = regular_event_files(season_dir, year)
    halves = list(group_half_innings(read_events(cwevent, season_dir, year)))

    totals: defaultdict[str, int] = defaultdict(int)
    for half in halves:
        for event in half:
            totals["r"] += event.runs
            totals["er"] += event.earned_runs
            totals["outs"] += event.outs_on_play
            if not event.batter_event:
                continue
            totals["pa"] += 1
            totals["ab"] += int(event.at_bat)
            totals["h"] += int(event.hit_value > 0)
            totals["doubles"] += int(event.hit_value == 2)
            totals["triples"] += int(event.hit_value == 3)
            totals["hr"] += int(event.hit_value == 4)
            totals["bb"] += int(event.event_code in (EVENT_WALK, EVENT_INTENTIONAL_WALK))
            totals["ibb"] += int(event.event_code == EVENT_INTENTIONAL_WALK)
            totals["hbp"] += int(event.event_code == EVENT_HBP)
            totals["sf"] += int(event.sacrifice_fly)
            totals["k"] += int(event.event_code == 3)

    complete_halves = [
        half for half in halves if half[-1].outs_before + half[-1].outs_on_play >= 3
    ]
    re_sum: defaultdict[tuple[int, int], float] = defaultdict(float)
    re_count: defaultdict[tuple[int, int], int] = defaultdict(int)
    for half in complete_halves:
        inning_runs = sum(event.runs for event in half)
        runs_before = 0
        for event in half:
            if event.batter_event:
                re_sum[event.state] += inning_runs - runs_before
                re_count[event.state] += 1
            runs_before += event.runs

    if len(re_count) != 24 or any(count == 0 for count in re_count.values()):
        raise ValueError(f"{year}: incomplete RE24 state coverage")
    run_expectancy = {state: re_sum[state] / re_count[state] for state in re_count}

    value_sum: defaultdict[str, float] = defaultdict(float)
    value_count: defaultdict[str, int] = defaultdict(int)
    event_names = {event_code: name for name, event_code in WEIGHT_EVENTS.items()}
    for half in complete_halves:
        for index, event in enumerate(half):
            if not event.batter_event:
                continue
            event_name = event_names.get(event.event_code)
            if event_name is None and event.outs_on_play > 0:
                event_name = "out"
            if event_name is None:
                continue
            terminal = event.outs_before + event.outs_on_play >= 3
            after = 0.0 if terminal else run_expectancy[half[index + 1].state]
            run_value = event.runs + after - run_expectancy[event.state]
            value_sum[event_name] += run_value
            value_count[event_name] += 1

    average_values = {
        name: value_sum[name] / value_count[name] for name in (*WEIGHT_EVENTS, "out")
    }
    raw_weights = {
        name: average_values[name] - average_values["out"] for name in WEIGHT_EVENTS
    }

    denominator = totals["ab"] + totals["bb"] - totals["ibb"] + totals["sf"] + totals["hbp"]
    obp_denominator = totals["ab"] + totals["bb"] + totals["hbp"] + totals["sf"]
    lg_obp = (totals["h"] + totals["bb"] + totals["hbp"]) / obp_denominator
    singles = totals["h"] - totals["doubles"] - totals["triples"] - totals["hr"]
    counts = {
        "w_bb": totals["bb"] - totals["ibb"],
        "w_hbp": totals["hbp"],
        "w_1b": singles,
        "w_2b": totals["doubles"],
        "w_3b": totals["triples"],
        "w_hr": totals["hr"],
    }
    raw_lg_woba = sum(raw_weights[name] * counts[name] for name in WEIGHT_EVENTS) / denominator
    woba_scale = lg_obp / raw_lg_woba
    weights = {name: raw_weights[name] * woba_scale for name in WEIGHT_EVENTS}
    lg_woba = sum(weights[name] * counts[name] for name in WEIGHT_EVENTS) / denominator

    total_bases = singles + 2 * totals["doubles"] + 3 * totals["triples"] + 4 * totals["hr"]
    innings = totals["outs"] / 3.0
    lg_era = 9.0 * totals["er"] / innings
    raw_fip = (
        13 * totals["hr"] + 3 * (totals["bb"] + totals["hbp"]) - 2 * totals["k"]
    ) / innings
    lg_r_pa = totals["r"] / totals["pa"]

    return {
        "season": year,
        "source_sha256": source_digest(files),
        "lg_obp": lg_obp,
        "lg_slg": total_bases / totals["ab"],
        "lg_era": lg_era,
        "lg_fip": lg_era,
        "lg_woba": lg_woba,
        "woba_scale": woba_scale,
        "c_fip": lg_era - raw_fip,
        "lg_r_pa": lg_r_pa,
        "lg_wrc_pa": lg_r_pa,
        **weights,
    }


def render_rust(rows: list[dict[str, float | int | str]], revision: str) -> str:
    first = rows[0]["season"]
    last = rows[-1]["season"]
    lines = [
        "// @generated by scripts/generate_season_constants.py; do not edit by hand.",
        "/// Chadwick Bureau Retrosheet source revision used for generation.",
        f'pub const RETROSHEET_REVISION: &str = "{revision}";',
        "/// Earliest bundled completed MLB season.",
        f"pub const FIRST_SEASON: u16 = {first};",
        "/// Latest bundled completed MLB season.",
        f"pub const LAST_SEASON: u16 = {last};",
        "",
        "const SEASONS: &[SeasonConstants] = &[",
    ]
    fields = (
        "lg_obp", "lg_slg", "lg_era", "lg_fip", "lg_woba", "woba_scale",
        "c_fip", "lg_r_pa", "lg_wrc_pa", "w_bb", "w_hbp", "w_1b", "w_2b",
        "w_3b", "w_hr",
    )
    for row in rows:
        lines.append("    SeasonConstants {")
        lines.append(f'        source_sha256: "{row["source_sha256"]}",')
        lines.append(f'        season: {row["season"]},')
        for field in fields:
            lines.append(f"        {field}: {float(row[field]):.12},")
        lines.append("    },")
    lines.extend(["];", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrosheet-dir", required=True, type=Path)
    parser.add_argument("--cwevent", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--first-season", type=int, default=2010)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = [
        derive_year(args.cwevent, args.retrosheet_dir, year)
        for year in range(args.first_season, args.last_season + 1)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_rust(rows, args.revision))


if __name__ == "__main__":
    main()
