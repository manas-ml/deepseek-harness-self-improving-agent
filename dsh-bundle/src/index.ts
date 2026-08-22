/**
 * Cross-session task-family memory: two model-facing tools backed by the
 * Cordis storage-domain plugin (`ctx.storageDomain`), so reflections and
 * skill-version history survive across separate `dsh` sessions on disk,
 * not just for the lifetime of one run.
 * @module dsh-csv-anomaly-memory
 */

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { taskMemoryDomainSpec, reflectionRowSchema, skillVersionRowSchema } from './spec.js'
import type { ReflectionRow, SkillVersionRow } from './spec.js'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'tool-task-memory'

/** Services required: the model-facing tool registry and the storage-domain facility. */
export const inject = ['tools', 'storageDomain']

/**
 * Open the task-memory domain and register `record_reflection`,
 * `record_skill_version`, and `recall_task_memory`.
 * @param ctx - the plugin context; the domain closes on effect teardown.
 */
export async function apply(ctx: Context): Promise<void> {
  const domain = await ctx.storageDomain.open(taskMemoryDomainSpec)
  ctx.effect(() => async () => {
    await domain.close()
  }, 'tool-task-memory.domainClose')

  const reflections = domain.table('reflections')
  const skillVersions = domain.table('skill_versions')

  ctx.tools.register(defineTool({
    name: 'record_reflection',
    description:
      'Persist a reflection to durable cross-session memory: what a run observed, and what the agent did about it '
      + '(e.g. distilling a cold-start approach into a skill, or versioning a skill after a gap). Survives across '
      + 'separate dsh sessions.',
    parameters: {
      run_id: { type: 'string', required: true, description: 'Identifier of the run this reflection is about, e.g. "run-3".' },
      observation: { type: 'string', required: true, description: 'What was noticed (a gap, a pattern, a working approach).' },
      action: { type: 'string', required: true, description: 'What the agent did in response.' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const row: ReflectionRow = {
        runId: args.run_id,
        observation: args.observation,
        action: args.action,
        recordedAt: Date.now(),
      }
      reflectionRowSchema.parse(row)
      await reflections.put(`reflection:${args.run_id}`, row)
      return `recorded reflection for ${args.run_id}`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'record_skill_version',
    description:
      'Persist a skill-version record to durable cross-session memory: which skill/version was created, what it was '
      + 'based on, and why. Call this whenever you version a skill (e.g. csv-anomaly-check v1 -> v2) so the reason '
      + 'survives for future sessions.',
    parameters: {
      skill_name: { type: 'string', required: true, description: 'The skill\'s name, e.g. "csv-anomaly-check".' },
      version: { type: 'string', required: true, description: 'The new version, e.g. "v2".' },
      reason: { type: 'string', required: true, description: 'Why this version was created (the gap it fixes).' },
      based_on: { type: 'string', description: 'The prior version this was based on, e.g. "v1".' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const row: SkillVersionRow = {
        skillName: args.skill_name,
        version: args.version,
        reason: args.reason,
        recordedAt: Date.now(),
        ...(args.based_on === undefined ? {} : { basedOn: args.based_on }),
      }
      skillVersionRowSchema.parse(row)
      await skillVersions.put(`skill:${args.skill_name}@${args.version}`, row)
      return `recorded ${args.skill_name} ${args.version}`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'recall_task_memory',
    description:
      'Read back every reflection and skill-version record persisted so far across all previous sessions. Call this '
      + 'at the start of a session on this task family, before re-deriving anything, to see what earlier sessions '
      + 'already learned.',
    parameters: {},
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute() {
      const reflectionRows = [...reflections.entries()].map(([, row]) => row)
      const skillVersionRows = [...skillVersions.entries()].map(([, row]) => row)
      return JSON.stringify({ reflections: reflectionRows, skillVersions: skillVersionRows }, null, 2)
    },
  }))
}
