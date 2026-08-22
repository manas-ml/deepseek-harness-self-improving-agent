"""Reflection + skill versioning.

`bootstrap_v1()` is the one-time distillation step: after run-1, the agent
looks at what it did by hand (see agent/templates/skill_v1.py, which
encodes exactly the checks the cold-start session performed) and saves it
as a real, callable skill plugin.

`version_skill()` is what happens when a later run's file exposes a gap in
the current skill: rather than patch the anomaly ad hoc, the agent edits a
*copy* of the skill (locating a named anchor block and rewriting it), saves
it as the next version, and records why in memory-store/. This keeps every
version a genuine, inspectable diff instead of a re-save.
"""
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _read(path):
    with open(path) as f:
        return f.read()


def _write(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _append_reflection(memory_dir, entry):
    path = Path(memory_dir) / "reflections.jsonl"
    Path(memory_dir).mkdir(parents=True, exist_ok=True)
    entry = dict(entry)
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _update_skill_metadata(memory_dir, skill_entry):
    path = Path(memory_dir) / "skill_metadata.json"
    Path(memory_dir).mkdir(parents=True, exist_ok=True)
    data = {"skills": []}
    if path.exists():
        with open(path) as f:
            data = json.load(f)
    data["skills"].append(skill_entry)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _update_registry(skills_dir, name, version, version_dir, trigger_keywords, description):
    reg_path = Path(skills_dir) / "registry.json"
    registry = {"skills": []}
    if reg_path.exists():
        with open(reg_path) as f:
            registry = json.load(f)
    entries = [e for e in registry["skills"] if e["name"] != name]
    entries.append({
        "name": name,
        "latest_version": version,
        "latest_version_dir": version_dir,
        "trigger_keywords": trigger_keywords,
        "description": description,
    })
    registry["skills"] = entries
    with open(reg_path, "w") as f:
        json.dump(registry, f, indent=2)


def bootstrap_v1(run_id, skills_dir, memory_dir):
    """Distill run-1's manual checks into skills/csv-anomaly-check-v1."""
    dest_dir = Path(skills_dir) / "csv-anomaly-check-v1"
    _write(dest_dir / "skill.py", _read(TEMPLATES_DIR / "skill_v1.py"))
    _write(dest_dir / "SKILL.md", _read(TEMPLATES_DIR / "SKILL_v1.md"))

    _update_registry(
        skills_dir, "csv-anomaly-check", "v1", "csv-anomaly-check-v1",
        trigger_keywords=[
            "csv", "vendor", "anomaly", "anomalies", "data issue",
            "data issues", "export", "data quality", "vendor export",
        ],
        description="Flags missing values, duplicate rows, out-of-range "
                     "numbers, malformed dates, and shifted columns in "
                     "vendor-export CSVs.",
    )
    _update_skill_metadata(memory_dir, {
        "name": "csv-anomaly-check", "version": "v1",
        "created_from_run": run_id, "reason": "initial distillation of cold-start approach",
    })
    _append_reflection(memory_dir, {
        "run_id": run_id,
        "observation": "Cold-start session manually checked for missing "
                        "cells, duplicate rows, out-of-range numbers, "
                        "malformed dates, and non-numeric quantity fields, "
                        "in that order, using ad hoc inline code.",
        "action": "Distilled the approach into skills/csv-anomaly-check-v1, "
                   "a callable check(csv_path) function, so future sessions "
                   "reuse it instead of re-deriving it.",
    })
    return dest_dir


def _bump_version(version):
    n = int(version.lstrip("v"))
    return f"v{n + 1}"


def _replace_anchor(source, anchor_name, new_block):
    pattern = re.compile(
        rf"# --- {anchor_name}_ANCHOR ---.*?# --- END_{anchor_name}_ANCHOR ---",
        re.DOTALL,
    )
    if not pattern.search(source):
        raise ValueError(f"anchor {anchor_name} not found")
    return pattern.sub(new_block.strip("\n"), source, count=1)


def _bump_changelog(source, version, note):
    return source.replace("Changelog:\n", f"Changelog:\n  {version} - {note}\n", 1)


def version_skill(prev_version_dir, run_id, gap_description, patch_fn,
                   skills_dir, memory_dir, name="csv-anomaly-check"):
    """Copy prev skill, apply `patch_fn(source) -> (new_source, note)`, save as next version."""
    prev_version_dir = Path(prev_version_dir)
    prev_version = _read(prev_version_dir / "skill.py")
    m = re.search(r'VERSION = "(v\d+)"', prev_version)
    prev_v = m.group(1)
    new_v = _bump_version(prev_v)

    new_source, note = patch_fn(prev_version)
    new_source = new_source.replace(f'VERSION = "{prev_v}"', f'VERSION = "{new_v}"')
    new_source = _bump_changelog(new_source, new_v, note)

    new_dir = Path(skills_dir) / f"{name}-{new_v}"
    _write(new_dir / "skill.py", new_source)

    old_md = _read(prev_version_dir / "SKILL.md") if (prev_version_dir / "SKILL.md").exists() else ""
    new_md = old_md + f"\n## {new_v}\n\n**Trigger:** {gap_description}\n\n**Fix:** {note}\n"
    new_md = re.sub(rf"\({prev_v}\)", f"({new_v})", new_md, count=1)
    _write(new_dir / "SKILL.md", new_md)

    _update_registry(
        skills_dir, name, new_v, f"{name}-{new_v}",
        trigger_keywords=[
            "csv", "vendor", "anomaly", "anomalies", "data issue",
            "data issues", "export", "data quality", "vendor export",
        ],
        description=f"Flags missing values, duplicate rows, out-of-range "
                     f"numbers, malformed dates, and shifted columns in "
                     f"vendor-export CSVs. ({new_v})",
    )
    _update_skill_metadata(memory_dir, {
        "name": name, "version": new_v, "created_from_run": run_id,
        "based_on": prev_v, "reason": gap_description,
    })
    _append_reflection(memory_dir, {
        "run_id": run_id,
        "observation": gap_description,
        "action": f"Versioned {name} {prev_v} -> {new_v}: {note}",
    })
    return new_dir, new_v


# --- concrete patch functions for each known gap ---

def patch_add_sentinel_missing_values(source):
    new_block = (
        "# --- MISSING_VALUE_TOKENS_ANCHOR ---\n"
        'MISSING_VALUE_TOKENS = {"", "NULL", "N/A", "-", "--", "NaN", "null", "n/a"}\n'
        "# --- END_MISSING_VALUE_TOKENS_ANCHOR ---"
    )
    note = ("missing-value check only recognized truly empty cells; vendor "
            "files also use sentinel placeholders (NULL, N/A, -, --, NaN) "
            "which slipped through. Expanded MISSING_VALUE_TOKENS to cover them.")
    return _replace_anchor(source, "MISSING_VALUE_TOKENS", new_block), note


def patch_flag_zero_price_and_quantity(source):
    new_block = '''# --- OUT_OF_RANGE_ANCHOR ---
def _quantity_out_of_range(value):
    try:
        q = int(value)
    except (TypeError, ValueError):
        return False  # non-numeric is a shifted-column concern, not ours
    return q <= 0 or q > 1000


def _price_out_of_range(value):
    try:
        p = float(value)
    except (TypeError, ValueError):
        return False
    return p <= 0 or p > 100000
# --- END_OUT_OF_RANGE_ANCHOR ---'''
    note = ("out-of-range check treated 0 as a valid quantity/price, but a "
            "$0.00 line item or 0-unit order is a data error in this vendor "
            "feed. Changed the negative-only bound (`< 0`) to `<= 0` for "
            "both fields.")
    return _replace_anchor(source, "OUT_OF_RANGE", new_block), note


def patch_add_currency_symbol_check(source):
    """Stretch: a genuinely novel anomaly type v3 has no code path for at all."""
    if "_has_currency_symbol" in source:
        return source, "currency-symbol check already present"

    func = (
        "\n\n_CURRENCY_SYMBOLS = ('$', '\\u20ac', '\\u00a3')\n\n\n"
        "def _has_currency_symbol(value):\n"
        "    return isinstance(value, str) and value.strip().startswith(_CURRENCY_SYMBOLS)\n"
    )
    source = source.replace("\ndef check(csv_path):", func + "\ndef check(csv_path):")

    call = (
        '        if _has_currency_symbol(row.get("unit_price")):\n'
        '            anomalies.append({\n'
        '                "type": "currency_symbol", "row_id": row_id, "field": "unit_price",\n'
        '                "detail": f"unit_price={row.get(\'unit_price\')!r}",\n'
        "            })\n"
        "        # --- END_CHECK_LOOP_BODY_ANCHOR ---"
    )
    source = source.replace("        # --- END_CHECK_LOOP_BODY_ANCHOR ---", call)
    note = ("no existing check covered currency symbols embedded in "
            "unit_price (e.g. '$45.00', '\\u20ac12.50') -- a genuinely new "
            "anomaly category, not a variant of one already handled. Added "
            "_has_currency_symbol() and a new currency_symbol check.")
    return source, note
