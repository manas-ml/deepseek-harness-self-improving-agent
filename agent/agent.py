#!/usr/bin/env python3
"""Main session runner.

Simulates one agent session against one sample file: `--mode cold` performs
the manual, ad-hoc exploration a brand-new agent would do with no skills
available (run-1 only). `--mode auto` runs session-start skill discovery
first and, if a matching skill exists, uses it -- versioning it on the spot
if a sanity-scan turns up a gap it doesn't cover.

Every tool call is logged to a Trajectory and dumped to runs/run-N.json;
one row is appended to metrics.csv.
"""
import argparse
import csv as csv_module
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "task-family"))

from common import Trajectory, timed, write_report, sanity_scan  # noqa: E402
import discover as discover_mod  # noqa: E402
import reflect  # noqa: E402
import regression_guard  # noqa: E402
from checker import grade  # noqa: E402

SKILLS_DIR = ROOT / "skills"
MEMORY_DIR = ROOT / "memory-store"
RUNS_DIR = ROOT / "runs"
REPORTS_DIR = ROOT / "runs" / "reports"
METRICS_PATH = ROOT / "metrics.csv"
SOLVED_SAMPLES_PATH = MEMORY_DIR / "solved_samples.json"

GAP_PATCHES = {
    "sentinel_missing": (
        reflect.patch_add_sentinel_missing_values,
        "sanity scan found sentinel placeholder values (NULL/N/A/-/--/NaN) "
        "in sku/quantity/unit_price cells that the missing-value check "
        "didn't recognize.",
    ),
    "zero_value": (
        reflect.patch_flag_zero_price_and_quantity,
        "sanity scan found quantity or unit_price values of exactly 0, "
        "which the out-of-range check currently treats as valid.",
    ),
    "currency_symbol": (
        reflect.patch_add_currency_symbol_check,
        "sanity scan found unit_price values prefixed with a currency "
        "symbol ($/€/£) -- a category with no existing check at all.",
    ),
}


def load_solved_samples():
    if SOLVED_SAMPLES_PATH.exists():
        with open(SOLVED_SAMPLES_PATH) as f:
            return json.load(f)
    return []


def save_solved_samples(samples):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(SOLVED_SAMPLES_PATH, "w") as f:
        json.dump(samples, f, indent=2)


def cold_start_run(run_id, sample_csv, prompt):
    """Run-1 only: no skills exist yet, so the agent explores by hand."""
    traj = Trajectory(run_id, sample_csv, prompt)
    anomalies = []

    with timed() as t:
        exists = Path(sample_csv).exists()
    traj.step("list_input_file", str(sample_csv), f"exists={exists}", t.duration)

    with timed() as t:
        with open(sample_csv, newline="") as f:
            rows = list(csv_module.DictReader(f))
    traj.step("read_csv_rows", str(sample_csv), f"{len(rows)} rows", t.duration)
    time.sleep(0.08)

    with timed() as t:
        header = list(rows[0].keys()) if rows else []
        expected = ["row_id", "order_id", "sku", "product_name", "quantity",
                    "unit_price", "order_date", "warehouse"]
        schema_ok = header == expected
    traj.step("inspect_schema", "compare header to expected columns",
              f"schema_ok={schema_ok}", t.duration)
    time.sleep(0.1)

    with timed() as t:
        for row in rows:
            for field in ("sku", "quantity", "unit_price"):
                if row.get(field, "") == "":
                    anomalies.append({"type": "missing_value", "row_id": row["row_id"],
                                       "field": field, "detail": "empty cell"})
    traj.step("check_missing_values", "scan sku/quantity/unit_price for empty cells",
              f"{sum(1 for a in anomalies if a['type']=='missing_value')} found", t.duration)
    time.sleep(0.12)

    with timed() as t:
        seen = set()
        for row in rows:
            key = tuple(v for k, v in row.items() if k != "row_id")
            if key in seen:
                anomalies.append({"type": "duplicate_row", "row_id": row["row_id"],
                                   "field": None, "detail": "exact duplicate row"})
            else:
                seen.add(key)
    traj.step("check_duplicate_rows", "hash full rows, compare to earlier rows",
              f"{sum(1 for a in anomalies if a['type']=='duplicate_row')} found", t.duration)
    time.sleep(0.12)

    with timed() as t:
        for row in rows:
            try:
                q = int(row["quantity"])
                if q < 0 or q > 1000:
                    anomalies.append({"type": "out_of_range", "row_id": row["row_id"],
                                       "field": "quantity", "detail": f"quantity={q}"})
            except (TypeError, ValueError):
                pass
            try:
                p = float(row["unit_price"])
                if p < 0 or p > 100000:
                    anomalies.append({"type": "out_of_range", "row_id": row["row_id"],
                                       "field": "unit_price", "detail": f"unit_price={p}"})
            except (TypeError, ValueError):
                pass
    traj.step("check_out_of_range", "bounds-check quantity/unit_price",
              f"{sum(1 for a in anomalies if a['type']=='out_of_range')} found", t.duration)
    time.sleep(0.12)

    # First attempt at date checking assumes ISO format outright -- this is
    # the "wrong assumption" every cold-start session makes once.
    error_hit = False
    with timed() as t:
        try:
            from datetime import datetime
            for row in rows:
                datetime.strptime(row["order_date"], "%Y-%m-%d")
        except ValueError as e:
            error_hit = True
            error_msg = str(e)
    traj.step("attempt_parse_dates_assuming_iso", "datetime.strptime every order_date",
              f"ValueError: {error_msg}" if error_hit else "all parsed", t.duration,
              error=error_hit)
    time.sleep(0.08)

    with timed() as t:
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for row in rows:
            if not date_re.match(row.get("order_date", "")):
                anomalies.append({"type": "malformed_date", "row_id": row["row_id"],
                                   "field": "order_date", "detail": f"order_date={row['order_date']!r}"})
    traj.step("fix_and_check_malformed_dates",
              "switch to a regex format check instead of a bare strptime",
              f"{sum(1 for a in anomalies if a['type']=='malformed_date')} found", t.duration)
    time.sleep(0.12)

    with timed() as t:
        for row in rows:
            try:
                int(row["quantity"])
            except (TypeError, ValueError):
                if row["quantity"] != "":
                    anomalies.append({"type": "shifted_column", "row_id": row["row_id"],
                                       "field": "quantity",
                                       "detail": f"non-numeric quantity={row['quantity']!r}"})
    traj.step("check_shifted_columns", "confirm quantity parses as a number",
              f"{sum(1 for a in anomalies if a['type']=='shifted_column')} found", t.duration)
    time.sleep(0.12)

    with timed() as t:
        pass
    traj.step("aggregate_findings", f"{len(rows)} rows scanned", f"{len(anomalies)} anomalies", t.duration)

    report_path = REPORTS_DIR / f"{run_id}.report.json"
    with timed() as t:
        report = write_report(anomalies, sample_csv, report_path)
    traj.step("write_report", str(report_path), f"{len(anomalies)} anomalies written", t.duration)

    return traj, report, report_path


def auto_run(run_id, sample_csv, prompt):
    """Runs 2+: discover, invoke, sanity-check, and version the skill if needed."""
    traj = Trajectory(run_id, sample_csv, prompt)

    with timed() as t:
        entry, module = discover_mod.discover(prompt, SKILLS_DIR)
    if entry is None:
        traj.step("discover_skill", prompt, "no matching skill found", t.duration, error=True)
        raise RuntimeError("no skill found -- run bootstrap (cold start + reflect) first")
    traj.step("discover_and_load_skill", prompt,
              f"matched {entry['name']} {entry['latest_version']}", t.duration)
    time.sleep(0.02)

    current_version_dir = SKILLS_DIR / entry["latest_version_dir"]

    with timed() as t:
        result = module.check(str(sample_csv))
    traj.step(f"invoke_skill.check ({entry['latest_version']})", str(sample_csv),
              f"{len(result['anomalies_found'])} anomalies found", t.duration)
    time.sleep(0.02)

    with timed() as t:
        gaps = sanity_scan(sample_csv, result)
    traj.step("sanity_scan", "cross-check raw values against report",
              f"gaps={gaps}" if gaps else "no gaps found", t.duration)
    time.sleep(0.03)

    final_version = entry["latest_version"]
    for gap in gaps:
        if gap not in GAP_PATCHES:
            continue
        patch_fn, gap_description = GAP_PATCHES[gap]

        with timed() as t:
            new_dir, new_version = reflect.version_skill(
                current_version_dir, run_id, gap_description, patch_fn,
                SKILLS_DIR, MEMORY_DIR,
            )
        traj.step("reflect_and_version_skill",
                  f"gap={gap}, base={final_version}",
                  f"wrote {new_dir.name} ({new_version})", t.duration)
        time.sleep(0.05)

        solved = load_solved_samples()
        with timed() as t:
            guard_result = regression_guard.replay(new_dir, solved, RUNS_DIR / "tmp_regression")
        traj.step("regression_guard_replay",
                  f"replay {new_version} against {len(solved)} prior sample(s)",
                  f"passed={guard_result['passed']}", t.duration,
                  error=not guard_result["passed"])
        time.sleep(0.05)

        current_version_dir = new_dir
        final_version = new_version
        module = discover_mod._load_module(new_dir)

        with timed() as t:
            result = module.check(str(sample_csv))
        traj.step(f"invoke_skill.check ({new_version})", str(sample_csv),
                  f"{len(result['anomalies_found'])} anomalies found", t.duration)
        time.sleep(0.02)

    report_path = REPORTS_DIR / f"{run_id}.report.json"
    with timed() as t:
        report = write_report(result["anomalies_found"], sample_csv, report_path)
    traj.step("write_report", str(report_path), f"{len(result['anomalies_found'])} anomalies written", t.duration)

    return traj, report, report_path, final_version


def append_metrics_row(run_id, tool_calls, wall_clock, errors, skill_version, correct):
    is_new = not METRICS_PATH.exists()
    with open(METRICS_PATH, "a", newline="") as f:
        w = csv_module.writer(f)
        if is_new:
            w.writerow(["run_id", "tool_calls", "wall_clock_seconds", "errors_encountered",
                        "skill_version_used", "correct"])
        w.writerow([run_id, tool_calls, f"{wall_clock:.4f}", errors, skill_version,
                    "y" if correct else "n"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--sample", required=True)
    p.add_argument("--mode", choices=["cold", "auto"], required=True)
    p.add_argument("--prompt", default="Check this vendor export for data issues and produce a report.")
    p.add_argument("--bootstrap-after", action="store_true",
                   help="After a cold run, distill it into skills/csv-anomaly-check-v1.")
    args = p.parse_args()

    sample_csv = Path(args.sample)
    meta_path = sample_csv.with_suffix(".meta.json")

    if args.mode == "cold":
        traj, report, report_path = cold_start_run(args.run_id, sample_csv, args.prompt)
        skill_version_used = "none"
    else:
        traj, report, report_path, skill_version_used = auto_run(args.run_id, sample_csv, args.prompt)

    grade_result = grade(meta_path, report_path)
    correct = grade_result["correct"]

    run_json_path = RUNS_DIR / f"{args.run_id}.json"
    traj.save(run_json_path, skill_version_used, correct)
    append_metrics_row(args.run_id, len(traj.steps), traj.elapsed(), traj.errors,
                        skill_version_used, correct)

    if correct:
        solved = load_solved_samples()
        if str(sample_csv) not in solved:
            solved.append(str(sample_csv))
            save_solved_samples(solved)

    if args.mode == "cold" and args.bootstrap_after:
        reflect.bootstrap_v1(args.run_id, SKILLS_DIR, MEMORY_DIR)

    print(json.dumps({
        "run_id": args.run_id, "tool_calls": len(traj.steps),
        "wall_clock_seconds": round(traj.elapsed(), 4), "errors": traj.errors,
        "skill_version_used": skill_version_used, "correct": correct,
        "grade": grade_result,
    }, indent=2))


if __name__ == "__main__":
    main()
