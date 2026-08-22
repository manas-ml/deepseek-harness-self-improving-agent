# dsh-csv-anomaly-memory

A real, installable [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
plugin **bundle** (the mechanism documented at
[`docs/user/develop/basic/publish.md`](https://github.com/deepseek-ai/deepseek-harness/blob/main/docs/user/develop/basic/publish.md)
in that repo) for the "gets better with practice" task family in this repo.
It adds durable cross-session memory on top of the harness's default agent
stack (`@deepseek-ai/dsh-base`, which already mounts `skill`,
`skill-filesystem`, and `tool-skill`).

## What this actually is

- `package.json` — a bundle manifest (`dsh.bundle.patch`), depending on the
  **real, published** `@deepseek-ai/dsh-storage`, `@deepseek-ai/dsh-storage-json`,
  `@deepseek-ai/dsh-storage-domain`, and `@deepseek-ai/dsh-tools` npm packages
  (pinned to `0.1.1-rc.2`, the current `next`-tagged prerelease at the time
  this was written — DeepSeek Harness is developer preview, so packages
  publish under `next`, not `latest`; check
  `npm view @deepseek-ai/dsh-storage-domain dist-tags` before reusing this).
- `cordis.patch.yml` — inserts the storage plugin chain (`storage` →
  `storage-json` → `storage-domain`, exactly the three rows used by the
  harness's own `dsh-web-app` bundle) plus this package's own
  `tool-task-memory` plugin row.
- `src/spec.ts` — a `defineDomain`/`domainTable` declaration (the
  `@deepseek-ai/dsh-storage-domain` pattern used by
  `packages/feedback/message-feedback` in the harness repo): two tables,
  `reflections` and `skill_versions`.
- `src/index.ts` — a Cordis plugin (`name`/`inject`/`apply`, the
  `docs/user/develop/basic/tool.md` shape) registering three `defineTool`
  tools: `record_reflection`, `record_skill_version`, `recall_task_memory`.
  This is what "wires the Cordis storage plugin so skills and memory survive
  across sessions" for real, not as a simulation.

The skill itself lives outside this directory, at the repository root's
`.dsh/skills/csv-anomaly-check-v1/` (`skill-filesystem`'s default
project-root discovery path — no plugin code needed for that part at all):
a `SKILL.md` plus a callable `check.py` the model invokes through the bash
tool. That script already runs standalone and passes the repo's own
`task-family/checker.py` (verified — see the root README).

## What's verified vs. what's unrun

**Verified, for real, in this environment:**
- `npm install` resolves every dependency against the actual npm registry —
  the packages exist and the versions are compatible.
- `npx tsc -p tsconfig.json --noEmit` typechecks `src/` clean against the
  real published `.d.ts` files for `@deepseek-ai/dsh-storage-domain`,
  `@deepseek-ai/dsh-tools`, and `@deepseek-ai/cordis` — the `Domain`/`KvTable`
  API calls, `defineTool` shape, and `ctx.effect` disposer pattern are all
  type-correct against the real framework, not guessed.
- `npx tsc -p tsconfig.json` builds real `lib/*.js` + `lib/*.d.ts` output.
- `.dsh/skills/csv-anomaly-check-v1/check.py` runs standalone and its report
  passes `task-family/checker.py` on a real sample file.

**Not verified — needs a real `dsh` install + a `DEEPSEEK_API_KEY`:**
- That `dsh plugin --profile <name> add ./dsh-bundle` actually links this
  package into a profile correctly.
- That `dsh --profile <name> --dump-config` shows the composed layer without
  error (this needs no API key and is the natural next verification step —
  see below).
- That a live model session actually discovers and calls these tools the way
  `SKILL.md` tells it to, and that the storage-domain writes/reads round-trip
  through a real `storage-json` backend on disk.

## How to actually run this

From the harness's own docs, once you have `dsh` installed and a
`DEEPSEEK_API_KEY`:

```sh
# from the repository root, so relative paths (task-family/, .dsh/skills/,
# ./.dsh-task-memory) resolve against it
cd deepseek-harness-self-improving-agent

npm install -g @deepseek-ai/dsh   # or: npx @deepseek-ai/dsh ...
dsh plugin --profile csv-anomaly add ./dsh-bundle
dsh --profile csv-anomaly --dump-config   # no API key needed -- sanity-check the composed layer first
DEEPSEEK_API_KEY=sk-... dsh --profile csv-anomaly \
  "Check task-family/samples/sample_01.csv for data issues and produce a report."
```

Repeat with a different sample file for the next run; `recall_task_memory`
and the on-disk `.dsh/skills/` files are what should make later runs faster,
exactly as `demo-script.md` walks through for the standalone Python
simulation at the repository root.
