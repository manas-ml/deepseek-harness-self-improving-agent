"""Session-start skill discovery.

Given the task prompt for a new session, look at skills/registry.json and
find a skill whose trigger keywords overlap with the prompt. This is what
lets runs 2+ find and use `csv-anomaly-check` automatically instead of
rediscovering the same approach from scratch.
"""
import importlib.util
import json
from pathlib import Path


def load_registry(skills_dir):
    reg_path = Path(skills_dir) / "registry.json"
    if not reg_path.exists():
        return {"skills": []}
    with open(reg_path) as f:
        return json.load(f)


def save_registry(skills_dir, registry):
    reg_path = Path(skills_dir) / "registry.json"
    with open(reg_path, "w") as f:
        json.dump(registry, f, indent=2)


def _load_module(skill_dir):
    skill_dir = Path(skill_dir)
    spec = importlib.util.spec_from_file_location(skill_dir.name, skill_dir / "skill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover(prompt, skills_dir, threshold=1):
    """Return (skill_entry, module) for the best-matching skill, or (None, None)."""
    registry = load_registry(skills_dir)
    prompt_tokens = set(prompt.lower().replace(",", " ").replace(".", " ").split())

    best = None
    best_score = 0
    for entry in registry.get("skills", []):
        keywords = set(k.lower() for k in entry.get("trigger_keywords", []))
        score = 0
        for kw in keywords:
            if " " in kw:
                if kw in prompt.lower():
                    score += 1
            elif kw in prompt_tokens:
                score += 1
        if score > best_score:
            best_score = score
            best = entry

    if best is None or best_score < threshold:
        return None, None

    latest_dir = Path(skills_dir) / best["latest_version_dir"]
    module = _load_module(latest_dir)
    return best, module
