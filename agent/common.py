"""Shared plumbing for the agent runner: trajectory logging + report I/O.

Every "tool call" the agent makes during a session -- reading a file,
running a check, invoking a skill, editing a skill, replaying the
regression set -- is logged as one Step. The full list becomes
runs/run-N.json: an inspectable, append-only record of what the agent
actually did, not a black box.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path


class Trajectory:
    def __init__(self, run_id, sample_file, prompt):
        self.run_id = run_id
        self.sample_file = sample_file
        self.prompt = prompt
        self.steps = []
        self.errors = 0
        self._t0 = time.time()

    def step(self, tool, input_summary, output_summary, duration_s, error=False):
        self.steps.append({
            "step": len(self.steps) + 1,
            "tool": tool,
            "input": input_summary,
            "output": output_summary,
            "duration_s": round(duration_s, 4),
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if error:
            self.errors += 1

    def elapsed(self):
        return time.time() - self._t0

    def to_dict(self, skill_version_used, correct):
        return {
            "run_id": self.run_id,
            "sample_file": str(self.sample_file),
            "prompt": self.prompt,
            "tool_calls": len(self.steps),
            "errors_encountered": self.errors,
            "wall_clock_seconds": round(self.elapsed(), 4),
            "skill_version_used": skill_version_used,
            "steps": self.steps,
        }

    def save(self, out_path, skill_version_used, correct):
        data = self.to_dict(skill_version_used, correct)
        data["correct"] = correct
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        return data


class timed:
    """Context manager that measures wall-clock duration of a block."""
    def __init__(self):
        self.duration = 0.0

    def __enter__(self):
        self._t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.duration = time.time() - self._t0
        return False


SENTINEL_TOKENS = {"null", "n/a", "-", "--", "nan"}
CURRENCY_PREFIXES = ("$", "€", "£")


def sanity_scan(csv_path, report):
    """Generic post-check pass: look for raw-value smells the report didn't
    explain. Doesn't use ground truth -- just pattern-matches things a
    careful reviewer would double-check by eye. Returns a list of gap tags.
    """
    import csv as csv_module

    flagged = {(a["type"], str(a["row_id"]), a.get("field")) for a in report["anomalies_found"]}
    with open(csv_path, newline="") as f:
        rows = list(csv_module.DictReader(f))

    gaps = set()
    for row in rows:
        row_id = row.get("row_id")

        for field in ("sku", "quantity", "unit_price"):
            val = (row.get(field) or "")
            if val.strip().lower() in SENTINEL_TOKENS and ("missing_value", row_id, field) not in flagged:
                gaps.add("sentinel_missing")

        for field in ("quantity", "unit_price"):
            val = row.get(field) or ""
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if num == 0 and ("out_of_range", row_id, field) not in flagged:
                gaps.add("zero_value")

        val = row.get("unit_price") or ""
        if val.strip().startswith(CURRENCY_PREFIXES):
            if not any(t == "currency_symbol" and rid == row_id for (t, rid, _f) in flagged):
                gaps.add("currency_symbol")

    return sorted(gaps)


def write_report(anomalies, sample_file, out_path):
    from collections import Counter
    summary = dict(Counter(a["type"] for a in anomalies))
    report = {
        "file": str(sample_file),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anomalies_found": anomalies,
        "summary": summary,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    return report
