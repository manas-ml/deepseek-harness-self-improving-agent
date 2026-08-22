#!/usr/bin/env python3
"""Success-criteria checker.

Grades an agent-produced report against the ground-truth `.meta.json`
sidecar for a sample file. This is what makes correctness measurable
independent of speed: a run is "correct" iff every injected anomaly was
flagged (extra/false-positive flags are reported but don't fail the run).
"""
import argparse
import json
from pathlib import Path


def load_ground_truth(meta_path):
    with open(meta_path) as f:
        meta = json.load(f)
    return {(a["type"], str(a["row_id"])) for a in meta["anomalies"]}


def load_found(report_path):
    with open(report_path) as f:
        report = json.load(f)
    return {(a["type"], str(a["row_id"])) for a in report["anomalies_found"]}


def grade(meta_path, report_path):
    truth = load_ground_truth(meta_path)
    found = load_found(report_path)
    missed = truth - found
    extra = found - truth
    correct = len(missed) == 0
    return {
        "correct": correct,
        "true_anomaly_count": len(truth),
        "found_count": len(found),
        "missed": sorted(missed),
        "extra": sorted(extra),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--meta", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()
    result = grade(args.meta, args.report)
    print(json.dumps(result, indent=2))
    if not result["correct"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
