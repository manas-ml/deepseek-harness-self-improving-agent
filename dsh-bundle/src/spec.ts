/**
 * Durable storage-domain declaration for cross-session task-family memory:
 * reflections distilled after a run, and the skill-version history those
 * reflections produced.
 * @module dsh-csv-anomaly-memory/spec
 */

import { z } from 'zod'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'

/** One reflection: what a run observed, and what the agent did about it. */
export const reflectionRowSchema = z.object({
  runId: z.string().min(1),
  observation: z.string().min(1),
  action: z.string().min(1),
  recordedAt: z.number().int().nonnegative(),
})

export type ReflectionRow = z.infer<typeof reflectionRowSchema>

/** One skill-version record: why it was created and what it was based on. */
export const skillVersionRowSchema = z.object({
  skillName: z.string().min(1),
  version: z.string().min(1),
  basedOn: z.string().optional(),
  reason: z.string().min(1),
  recordedAt: z.number().int().nonnegative(),
})

export type SkillVersionRow = z.infer<typeof skillVersionRowSchema>

/**
 * Task-family memory domain: two append-oriented tables surviving across
 * separate `dsh` sessions on the storage-domain substrate (`ctx.storageDomain`).
 * Keys are synthetic (`reflection:<runId>`, `skill:<skillName>@<version>`) so
 * repeat writes for the same run/version overwrite rather than duplicate.
 */
export const taskMemoryDomainSpec = defineDomain({
  name: 'csv_anomaly_task_memory',
  version: 0,
  tables: {
    reflections: domainTable<string, ReflectionRow>(reflectionRowSchema),
    skill_versions: domainTable<string, SkillVersionRow>(skillVersionRowSchema),
  },
})
