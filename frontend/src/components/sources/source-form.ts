import type { FieldPath } from 'react-hook-form'
import { z } from 'zod'
import {
  Severity,
  SourceType,
  type SchemaResolution,
  type SeverityMapping,
  type SourceCreate,
  type SourceRead,
  type SourceUpdate,
} from '@/api/generated/model'
import {
  createSourceBodyNameMax,
  createSourceBodySchemaResolutionTwoFieldMax,
  createSourceBodySchemaResolutionTwoFieldRegExp,
  createSourceBodySeverityFieldOneMax,
  createSourceBodySeverityFieldOneRegExp,
  createSourceBodySlugMax,
  createSourceBodySlugRegExp,
} from '@/api/generated/sources/sources.zod'
import type { BodyIssue } from '@/lib/validation-errors'

/** How a source picks the schema of each event: the `mode` of `SchemaResolution`. */
export type ResolutionMode = SchemaResolution['mode']

/** Label of each resolution mode in the form's segmented control. */
export const resolutionModeLabel = {
  fixed: 'One schema',
  discriminator: 'Picked by a field',
} as const satisfies Record<ResolutionMode, string>

/** Shown when a slug does not match the slug pattern (DOMAIN.md §1). */
export const SLUG_INVALID = 'Use lower case letters and digits, joined by single hyphens, at most 50 characters.'

const FIELD_PATH_INVALID = 'Use a field path such as type or error.code: letters, digits and underscores, joined by dots.'

/** Most severe first, as people read the select. */
export const SEVERITIES: readonly Severity[] = ['critical', 'error', 'warn', 'info', 'debug']

/** The default severity a new source gives events whose severity it cannot read (the API's default). */
const DEFAULT_SEVERITY: Severity = 'info'

const fieldPath = (max: number, pattern: RegExp) =>
  z.string().trim().max(max, `Use at most ${max} characters.`).regex(pattern, FIELD_PATH_INVALID)

/** Rows of a mapping editor must have distinct, non-empty values; adds an issue under each repeated value. */
function checkDistinct(rows: readonly { value: string }[], key: 'mapping' | 'severityValues', ctx: z.RefinementCtx) {
  const seen = new Set<string>()
  rows.forEach((row, index) => {
    if (seen.has(row.value)) {
      ctx.addIssue({ code: 'custom', path: [key, index, 'value'], message: 'This value is already in the list.' })
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
    mode: z.enum(['fixed', 'discriminator'] as const satisfies readonly ResolutionMode[]),
    schemaId: z.string(),
    discriminatorField: z.string().trim(),
    mapping: z.array(
      z.object({
        value: z.string().trim().min(1, 'Enter the value.'),
        schemaId: z.string().min(1, 'Pick a schema.'),
      }),
    ),
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
    switch (values.mode) {
      case 'fixed':
        if (values.schemaId === '') ctx.addIssue({ code: 'custom', path: ['schemaId'], message: 'Pick a schema.' })
        break
      case 'discriminator': {
        const field = fieldPath(createSourceBodySchemaResolutionTwoFieldMax, createSourceBodySchemaResolutionTwoFieldRegExp)
        const parsed = field.safeParse(values.discriminatorField)
        if (values.discriminatorField === '') {
          ctx.addIssue({ code: 'custom', path: ['discriminatorField'], message: 'Enter the field that names the schema.' })
        } else if (!parsed.success) {
          ctx.addIssue({ code: 'custom', path: ['discriminatorField'], message: parsed.error.issues[0]?.message ?? FIELD_PATH_INVALID })
        }
        // An empty mapping would reject every event; the API accepts it, the form does not.
        if (values.mapping.length === 0) {
          ctx.addIssue({ code: 'custom', path: ['mapping'], message: 'Add at least one value and its schema.' })
        }
        checkDistinct(values.mapping, 'mapping', ctx)
        break
      }
      default:
        values.mode satisfies never
    }
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
    checkDistinct(values.severityValues, 'severityValues', ctx)
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
  mode: 'fixed',
  schemaId: '',
  discriminatorField: '',
  mapping: [],
  severityField: '',
  severityValues: [],
  severityDefault: DEFAULT_SEVERITY,
  enabled: true,
}

/** Form values for an existing source. */
export function fromSource(source: SourceRead): SourceFormValues {
  const resolution = source.schema_resolution
  const common = {
    ...NEW_SOURCE,
    name: source.name,
    slug: source.slug,
    type: source.type,
    severityField: source.severity.field ?? '',
    severityValues: Object.entries(source.severity.values ?? {}).map(([value, severity]) => ({ value, severity })),
    severityDefault: source.severity.default ?? DEFAULT_SEVERITY,
    enabled: source.enabled,
  }
  switch (resolution.mode) {
    case 'fixed':
      return { ...common, mode: 'fixed', schemaId: resolution.schema_id }
    case 'discriminator':
      return {
        ...common,
        mode: 'discriminator',
        discriminatorField: resolution.field,
        mapping: Object.entries(resolution.mapping).map(([value, schemaId]) => ({ value, schemaId })),
      }
    default:
      return resolution satisfies never
  }
}

/** The `SchemaResolution` the form describes. */
export function toResolution(values: SourceFormOutput): SchemaResolution {
  switch (values.mode) {
    case 'fixed':
      return { mode: 'fixed', schema_id: values.schemaId }
    case 'discriminator':
      return {
        mode: 'discriminator',
        field: values.discriminatorField,
        mapping: Object.fromEntries(values.mapping.map(({ value, schemaId }) => [value, schemaId])),
      }
    default:
      return values.mode satisfies never
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
    schema_resolution: toResolution(values),
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
  const resolution = toResolution(values)
  if (!sameJson(resolution, toResolution(before))) update.schema_resolution = resolution
  const severity = toSeverity(values)
  if (!sameJson(severity, toSeverity(before))) update.severity = severity
  if (values.enabled !== before.enabled) update.enabled = values.enabled
  return update
}

/**
 * The form field a `422` error points at, or `root`. Pydantic puts the union tag in tagged-union paths
 * (`['schema_resolution', 'fixed', 'schema_id']`), so nested paths match on their last segment.
 */
export function sourceIssueField(path: BodyIssue['path']): FieldPath<SourceFormValues> | 'root' {
  const [head] = path
  const last = path.at(-1)
  switch (head) {
    case 'name':
    case 'slug':
    case 'type':
    case 'enabled':
      return head
    case 'schema_resolution':
      if (last === 'schema_id') return 'schemaId'
      if (last === 'field') return 'discriminatorField'
      return 'root'
    case 'severity':
      if (last === 'field') return 'severityField'
      if (last === 'default') return 'severityDefault'
      return 'root'
    default:
      return 'root'
  }
}
