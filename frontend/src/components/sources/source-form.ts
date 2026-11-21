import type { FieldPath } from 'react-hook-form'
import { z } from 'zod'
import {
  Severity,
  SourceType,
  type SeverityMapping,
  type SourceCreate,
  type SourceRead,
  type SourceUpdate,
} from '@/api/generated/model'
import {
  createSourceBodyNameMax,
  createSourceBodySeverityFieldOneMax,
  createSourceBodySeverityFieldOneRegExp,
  createSourceBodySlugMax,
  createSourceBodySlugRegExp,
} from '@/api/generated/sources/sources.zod'
import type { BodyIssue } from '@/lib/validation-errors'

/** Shown when a slug does not match the slug pattern (DOMAIN.md §1). */
export const SLUG_INVALID = 'Use lower case letters and digits, joined by single hyphens, at most 50 characters.'

const FIELD_PATH_INVALID = 'Use a field path such as type or error.code: letters, digits and underscores, joined by dots.'

/** Most severe first, as people read the select. */
export const SEVERITIES: readonly Severity[] = ['critical', 'error', 'warn', 'info', 'debug']

/** The default severity a new source gives events whose severity it cannot read (the API's default). */
const DEFAULT_SEVERITY: Severity = 'info'

const fieldPath = (max: number, pattern: RegExp) =>
  z.string().trim().max(max, `Use at most ${max} characters.`).regex(pattern, FIELD_PATH_INVALID)

/** Severity value rows must have distinct values; adds an issue under each repeated value. */
function checkDistinct(rows: readonly { value: string }[], ctx: z.RefinementCtx) {
  const seen = new Set<string>()
  rows.forEach((row, index) => {
    if (seen.has(row.value)) {
      ctx.addIssue({ code: 'custom', path: ['severityValues', index, 'value'], message: 'This value is already in the list.' })
    }
    seen.add(row.value)
  })
}

/** What the source dialog edits; `toCreate` and `toUpdate` turn it into the request body. */
export const sourceFormSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, 'Enter a source name.')
      .max(createSourceBodyNameMax, `Use at most ${createSourceBodyNameMax} characters.`),
    slug: z.string().min(1, 'Enter a slug.').max(createSourceBodySlugMax, SLUG_INVALID).regex(createSourceBodySlugRegExp, SLUG_INVALID),
    type: z.enum(SourceType),
    severityField: z.string().trim(),
    severityValues: z.array(
      z.object({
        value: z.string().trim().min(1, 'Enter the value.'),
        severity: z.enum(Severity),
      }),
    ),
    severityDefault: z.enum(Severity),
    enabled: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.severityField === '') {
      if (values.severityValues.length > 0) {
        ctx.addIssue({
          code: 'custom',
          path: ['severityField'],
          message: 'Enter the field that holds the severity, or remove the values below.',
        })
      }
    } else {
      const parsed = fieldPath(createSourceBodySeverityFieldOneMax, createSourceBodySeverityFieldOneRegExp).safeParse(
        values.severityField,
      )
      if (!parsed.success) {
        ctx.addIssue({ code: 'custom', path: ['severityField'], message: parsed.error.issues[0]?.message ?? FIELD_PATH_INVALID })
      }
    }
    checkDistinct(values.severityValues, ctx)
  })

/** Values of the source form before validation. */
export type SourceFormValues = z.input<typeof sourceFormSchema>

/** Values of the source form after validation (trimmed). */
export type SourceFormOutput = z.output<typeof sourceFormSchema>

/** Form values for a new source. */
export const NEW_SOURCE: SourceFormValues = {
  name: '',
  slug: '',
  type: 'webhook',
  severityField: '',
  severityValues: [],
  severityDefault: DEFAULT_SEVERITY,
  enabled: true,
}

/** Form values for an existing source. */
export function fromSource(source: SourceRead): SourceFormValues {
  return {
    name: source.name,
    slug: source.slug,
    type: source.type,
    severityField: source.severity.field ?? '',
    severityValues: Object.entries(source.severity.values ?? {}).map(([value, severity]) => ({ value, severity })),
    severityDefault: source.severity.default ?? DEFAULT_SEVERITY,
    enabled: source.enabled,
  }
}

/** The `SeverityMapping` the form describes; without a field every event gets the default. */
export function toSeverity(values: SourceFormOutput): SeverityMapping {
  if (values.severityField === '') return { field: null, values: {}, default: values.severityDefault }
  return {
    field: values.severityField,
    values: Object.fromEntries(values.severityValues.map(({ value, severity }) => [value, severity])),
    default: values.severityDefault,
  }
}

/** `POST /sources` body. */
export function toCreate(values: SourceFormOutput, teamId: string): SourceCreate {
  return {
    name: values.name,
    slug: values.slug,
    type: values.type,
    team_id: teamId,
    severity: toSeverity(values),
    enabled: values.enabled,
  }
}

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/**
 * `PATCH /sources/{id}` body with only the fields that differ from `source`; `null` means unchanged
 * (`SourceUpdate`), so unchanged fields are left out. Both sides go through the form, so key order matches.
 */
export function toUpdate(values: SourceFormOutput, source: SourceRead): SourceUpdate {
  const before = sourceFormSchema.parse(fromSource(source))
  const update: SourceUpdate = {}
  if (values.name !== before.name) update.name = values.name
  const severity = toSeverity(values)
  if (!sameJson(severity, toSeverity(before))) update.severity = severity
  if (values.enabled !== before.enabled) update.enabled = values.enabled
  return update
}

/** The form field a `422` error points at, or `root`; nested `severity` paths match on their last segment. */
export function sourceIssueField(path: BodyIssue['path']): FieldPath<SourceFormValues> | 'root' {
  const [head] = path
  const last = path.at(-1)
  switch (head) {
    case 'name':
    case 'slug':
    case 'type':
    case 'enabled':
      return head
    case 'severity':
      if (last === 'field') return 'severityField'
      if (last === 'default') return 'severityDefault'
      return 'root'
    default:
      return 'root'
  }
}
