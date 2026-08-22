"""Regression guard (stretch goal).

Before a new skill version is accepted, replay it against every
previously-solved sample file to confirm it doesn't break cases that used
to pass. This turns skill versioning into a gated update rather than a
blind overwrite.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "task-family"))
from checker import grade  # noqa: E402


def _load_module(skill_dir):
    skill_dir = Path(skill_dir)
    spec = importlib.util.spec_from_file_location(skill_dir.name + "_regr", skill_dir / "skill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(skill_dir, sample_csv_paths, tmp_dir):
    """Run the candidate skill against every prior sample; return a pass/fail report."""
    module = _load_module(skill_dir)
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    results = []
    all_pass = True
    for csv_path in sample_csv_paths:
        csv_path = Path(csv_path)
        meta_path = csv_path.with_suffix(".meta.json")
        result = module.check(str(csv_path))
        report_path = tmp_dir / f"{csv_path.stem}.report.json"
        with open(report_path, "w") as f:
            json.dump({"anomalies_found": result["anomalies_found"]}, f)
        grade_result = grade(meta_path, report_path)
        results.append({"sample": csv_path.name, **grade_result})
        if not grade_result["correct"]:
            all_pass = False

    return {"passed": all_pass, "results": results}
