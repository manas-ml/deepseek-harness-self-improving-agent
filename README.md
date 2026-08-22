# Gets Better With Practice -- Self-Improving Agent POC

A demo of experience-driven improvement: across repeated sessions on the
same task family, an agent gets measurably faster/cleaner because it
distills what worked into a reusable, saved skill -- not because any model
weights changed. Everything driving the improvement (the skill file, the
memory store, the trajectories) is inspectable, not a black box.

This build is a self-contained Python (stdlib-only) implementation -- no
external services required, `python3 agent/agent.py ...` runs a full
session end to end.

## Layout

- `task-family/` -- generator for synthetic vendor-export CSVs (`generate.py`),
  a schema (`schema.py`), a correctness checker (`checker.py`), and
  `samples/` (7 generated CSVs + `.meta.json` ground truth each).
- `agent/` -- the session runner. `agent.py` is the CLI entrypoint;
  `common.py` has trajectory logging + the generic sanity-scan;
  `discover.py` is session-start skill discovery; `reflect.py` distills
  run-1 into a skill and applies versioned patches when a gap is found;
  `regression_guard.py` replays a candidate skill version against every
  previously-solved sample before it's accepted; `templates/` holds the
  hand-authored v1 skill source that `reflect.bootstrap_v1()` copies into
  `skills/` after run-1 (kept out of `skills/` itself so run-1 starts with
  zero skill files, per the acceptance criteria).
- `skills/` -- versioned, callable skill plugins the agent writes for
  itself (`csv-anomaly-check-v1`, `v2`, ...), plus `registry.json` for
  discovery. Empty until run-1's reflection step runs.
- `memory-store/` -- persistent storage: `reflections.jsonl` (append-only
  observation/action log), `skill_metadata.json` (version history),
  `solved_samples.json` (regression-guard corpus). Empty until run-1.
- `runs/run-N.json` -- full captured trajectory per session.
- `runs/reports/` -- the anomaly report each session produced.
- `metrics.csv` -- one row per run: `run_id, tool_calls,
  wall_clock_seconds, errors_encountered, skill_version_used, correct`.
- `demo-script.md` -- presenter walkthrough.

## Quick start

```bash
# true cold start
rm -rf skills/* memory-store/* runs/* metrics.csv

python3 agent/agent.py --run-id run-1 --sample task-family/samples/sample_01.csv \
  --mode cold --bootstrap-after        # cold exploration, then distill skill v1

python3 agent/agent.py --run-id run-2 --sample task-family/samples/sample_02.csv --mode auto
python3 agent/agent.py --run-id run-3 --sample task-family/samples/sample_03.csv --mode auto
python3 agent/agent.py --run-id run-4 --sample task-family/samples/sample_04.csv --mode auto
python3 agent/agent.py --run-id run-5 --sample task-family/samples/sample_05.csv --mode auto
python3 agent/agent.py --run-id run-6 --sample task-family/samples/sample_06.csv --mode auto
python3 agent/agent.py --run-id run-7 --sample task-family/samples/sample_07.csv --mode auto  # stretch: novel anomaly + regression guard
```

Each invocation is one independent "session": it reads `skills/` and
`memory-store/` fresh from disk (no in-memory state carries over between
`agent.py` processes), does its work, and writes back to disk -- exactly
the persistence boundary the exercise asks for.

To grade any report by hand:
```bash
python3 task-family/checker.py --meta task-family/samples/sample_03.meta.json \
  --report runs/reports/run-3.report.json
```

## How the "learning" actually works

1. **Run 1 (cold start).** No skills exist. `agent.py --mode cold` performs
   11 ad hoc, hand-coded checks directly (see `agent/agent.py`'s
   `cold_start_run`) -- including a genuine wrong assumption (naive
   `datetime.strptime` on every date) that throws and gets corrected mid-run.
2. **Reflection.** `reflect.bootstrap_v1()` copies `agent/templates/skill_v1.py`
   (the same logic run-1 used, generalized into a `check(csv_path)`
   function) into `skills/csv-anomaly-check-v1/`, registers it in
   `skills/registry.json`, and logs the distillation to
   `memory-store/reflections.jsonl`.
3. **Discovery.** `agent/discover.py` matches a session's prompt against
   `registry.json`'s trigger keywords at session start -- this is how
   runs 2+ find the skill without being told where it is.
4. **Sanity scan + versioning.** After invoking a skill, `common.sanity_scan()`
   does a generic (no-ground-truth) pass over the raw CSV, looking for
   value patterns the report didn't explain (sentinel tokens, zero prices,
   currency symbols). If it finds one, `reflect.version_skill()` edits a
   *copy* of the current skill (via named anchor blocks in the source) and
   saves it as the next version -- a real code diff, not a re-save.
5. **Regression guard.** Before a new version is used, `regression_guard.replay()`
   runs it against every sample in `memory-store/solved_samples.json`
   (every previously-correct run) and only proceeds if none of them regress.

## Acceptance criteria checklist

- [x] Run 1 starts with zero skill files present (`skills/` and
      `memory-store/` are empty until run-1's reflection step).
- [x] Run 5 tool-call count is ~64% lower than run 1 (4 vs 11), correctness
      maintained -- see `metrics.csv`.
- [x] Skill version history (`v1 -> v2 -> v3 -> v4`) is real diffs with
      distinct root causes, not re-saves -- `diff -u
      skills/csv-anomaly-check-v1/skill.py skills/csv-anomaly-check-v2/skill.py`.
- [x] Run 6 (validation) solves a never-seen file correctly on the first
      try, at the same low tool-call count as run 5 -- proves generalization.
- [x] Deleting `skills/` and `memory-store/` and re-running run-1's prompt
      reproduces the identical 11-step, 1-error cold-start struggle --
      proves the improvement comes from the stored skill/memory.
- [x] **Stretch:** regression-gated skill updates (`agent/regression_guard.py`)
      -- run 7 feeds a genuinely novel anomaly type (currency symbols),
      watches v3 under-handle it, and watches the agent version to v4 and
      re-pass the full regression set before accepting it.

See `demo-script.md` for the full presenter walkthrough.
