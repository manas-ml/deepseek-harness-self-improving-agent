# Demo script: "Gets Better With Practice"

Presenter walkthrough for the self-improving-agent POC. Goal: show that the
agent gets measurably faster/cleaner across repeated sessions on the same
task family *because it saved a reusable skill*, not because any model
weights changed -- and that every part of that improvement (the skill file,
the memory store, the trajectories) is inspectable, not a black box.

Everything below is already captured in the repo (`runs/*.json`,
`metrics.csv`, `skills/`, `memory-store/`) from a real end-to-end pass. You
can present from the committed artifacts directly, or re-run any session
live with the commands shown.

## 0. Set the stage (30s)

> "This is a data-quality-checking agent. Every session gets a fresh vendor
> CSV export with the same *kinds* of problems -- missing values, bad
> ranges, duplicate rows, shifted columns, malformed dates -- but different
> specifics each time. Watch what happens to tool-call count and skill
> version across seven sessions."

Show `task-family/samples/` -- seven CSVs, each with a `.meta.json`
ground-truth sidecar (`task-family/checker.py` grades against this, so
correctness is measured independently of speed).

## 1. Run 1 -- cold start (no head start)

Show `skills/` and `memory-store/` are populated *now*, then point out that
run-1 started from genuinely empty directories (visible in
`runs/run-1.json`'s 11 steps -- there is no skill-discovery step at all).

Prompt used:
```
Check this vendor export for data issues and produce a report.
```

Command (already captured; re-runnable):
```
python3 agent/agent.py --run-id run-1 --sample task-family/samples/sample_01.csv \
  --mode cold --bootstrap-after
```

Open `runs/run-1.json` in the Trajectory view. Walk through the steps:
`list_input_file -> read_csv_rows -> inspect_schema -> check_missing_values
-> check_duplicate_rows -> check_out_of_range -> attempt_parse_dates_assuming_iso
(ValueError!) -> fix_and_check_malformed_dates -> check_shifted_columns ->
aggregate_findings -> write_report`.

**Point out:** 11 tool calls, 1 real error (the naive date-parsing attempt
throws, gets caught, and the agent switches strategy), 0.87s wall clock.
This is exploration -- the agent is discovering the approach live.

## 2. The reflection step

> "Rather than let this knowledge evaporate at the end of the session, the
> agent turns it into a real, callable tool."

Open `skills/csv-anomaly-check-v1/skill.py`. Point out it's not a prose
note -- it's the same checks from run-1, generalized into a `check(csv_path)`
function. Open `memory-store/reflections.jsonl` and read the run-1 entry:
what was observed, what action was taken.

## 3. Runs 2-3 -- the skill gets used, then extended

```
python3 agent/agent.py --run-id run-2 --sample task-family/samples/sample_02.csv --mode auto
python3 agent/agent.py --run-id run-3 --sample task-family/samples/sample_03.csv --mode auto
```

Run-2: open `runs/run-2.json` -- only 4 steps: `discover_and_load_skill ->
invoke_skill.check -> sanity_scan -> write_report`. No exploration, no
errors. Skill found and used automatically via `agent/discover.py`'s
keyword match against `skills/registry.json`.

Run-3: sample_03 uses **sentinel** missing-value placeholders (`NULL`,
`N/A`, `-`) instead of empty cells -- v1's missing-value check only knows
about empty strings, so it misses them. Watch `runs/run-3.json`: after
`invoke_skill.check (v1)`, `sanity_scan` reports `gaps=['sentinel_missing']`,
then `reflect_and_version_skill` writes `csv-anomaly-check-v2`, then
`regression_guard_replay` confirms v2 still passes on samples 01-02 before
it's used, then the skill re-runs and the report comes back clean.

**This is the moment to slow down.** The agent didn't hand-solve the
sentinel values for this one file -- it edited the *skill*.

## 4. The diff (the "what it learned" moment)

```
diff -u skills/csv-anomaly-check-v1/skill.py skills/csv-anomaly-check-v2/skill.py
```

Show the real, human-readable diff: `MISSING_VALUE_TOKENS = {""}` becomes
`{"", "NULL", "N/A", "-", "--", "NaN", "null", "n/a"}`, plus a changelog
line explaining *why*. Also open `skills/csv-anomaly-check-v2/SKILL.md` --
the trigger and fix are written in plain English.

Then run-4 (`sample_04.csv` has `$0.00` / `0`-unit line items that v2's
out-of-range check treats as valid) triggers a second, independent
versioning event: v2 -> v3. Show that diff too:
```
python3 agent/agent.py --run-id run-4 --sample task-family/samples/sample_04.csv --mode auto
diff -u skills/csv-anomaly-check-v2/skill.py skills/csv-anomaly-check-v3/skill.py
```
Two real refinements, two different root causes -- not the same fix saved
twice.

## 5. Runs 5-6 -- the payoff

```
python3 agent/agent.py --run-id run-5 --sample task-family/samples/sample_05.csv --mode auto
python3 agent/agent.py --run-id run-6 --sample task-family/samples/sample_06.csv --mode auto
```

Open `metrics.csv` side by side with run-1:

| run_id | tool_calls | wall_clock_seconds | errors | skill_version_used | correct |
|---|---|---|---|---|---|
| run-1 | 11 | 0.87 | 1 | none | y |
| run-5 | 4  | 0.07 | 0 | v3   | y |
| run-6 | 4  | 0.07 | 0 | v3   | y |

**Run 5 vs run 1: 4 vs 11 tool calls -- a 64% reduction, well past the ~30%
target, with correctness maintained.**

Run-6 uses `sample_06.csv`, a file the skill has never seen, generated
fresh, with sentinel missing values, zero-price items, and multiple
malformed dates all at once. It's solved correctly on the first try with
the same 4-step trajectory as run-5 -- proving the skill generalizes across
the task family rather than having memorized specific files.

## 6. Optional: the regression guard live (stretch)

Feed a deliberately novel anomaly type mid-demo: `sample_07.csv` has
`unit_price` values prefixed with currency symbols (`$45.00`, `€12.50`) --
a category v3 has *no code path for at all*, not a variant of something it
already checks.

```
python3 agent/agent.py --run-id run-7 --sample task-family/samples/sample_07.csv --mode auto
```

Watch `runs/run-7.json`: `invoke_skill.check (v3)` under-reports (misses
the currency anomalies), `sanity_scan` catches it (`gaps=['currency_symbol']`),
the agent versions to v4, and -- the key beat -- `regression_guard_replay`
replays v4 against **all six previously-solved samples** before accepting
it, confirming nothing that used to pass now breaks. Only then does it
re-run v4 on sample_07 and get a correct report.

```
diff -u skills/csv-anomaly-check-v3/skill.py skills/csv-anomaly-check-v4/skill.py
cat runs/run-7.json | python3 -m json.tool | grep -A1 regression_guard_replay
```

## 7. Prove it's the skill, not a fluke (closing beat)

> "If none of this is real -- if the speedup were coming from caching or
> luck -- deleting the skill and memory store should make no difference."

```
rm -rf skills/* memory-store/*
python3 agent/agent.py --run-id run-1-again --sample task-family/samples/sample_01.csv --mode cold
```

Show it reproduces the exact same 11-step, 1-error cold-start struggle from
step 1. The improvement lives entirely in `skills/` and `memory-store/` --
inspectable files, not model weights, not a black box.

(Afterwards, restore the real state with `git checkout -- skills memory-store
metrics.csv runs` or re-run the full sequence in order 1 through 7.)

## Appendix: full command sequence

```
rm -rf skills/* memory-store/* runs/* metrics.csv   # true cold start

python3 agent/agent.py --run-id run-1 --sample task-family/samples/sample_01.csv --mode cold --bootstrap-after
python3 agent/agent.py --run-id run-2 --sample task-family/samples/sample_02.csv --mode auto
python3 agent/agent.py --run-id run-3 --sample task-family/samples/sample_03.csv --mode auto
python3 agent/agent.py --run-id run-4 --sample task-family/samples/sample_04.csv --mode auto
python3 agent/agent.py --run-id run-5 --sample task-family/samples/sample_05.csv --mode auto
python3 agent/agent.py --run-id run-6 --sample task-family/samples/sample_06.csv --mode auto
python3 agent/agent.py --run-id run-7 --sample task-family/samples/sample_07.csv --mode auto   # stretch
```
