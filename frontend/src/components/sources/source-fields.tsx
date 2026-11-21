import { useState, type ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import { Plus, Trash2 } from 'lucide-react'
import { Controller, useFieldArray, useFormState, useWatch, type Control, type UseFormReturn } from 'react-hook-form'
import { SourceType, type Severity } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { sourceTypeHelp, sourceTypeLabel } from '@/lib/ingest-example'
import { severityIcon, severityLabel } from '@/lib/severity'
import { slugify } from '@/lib/slug'
import { SEVERITIES, type SourceFormOutput, type SourceFormValues } from './source-form'

/** The react-hook-form instance of the source dialog. */
export type SourceForm = UseFormReturn<SourceFormValues, unknown, SourceFormOutput>

const typeItems = Object.values(SourceType).map((value) => ({ value, label: sourceTypeLabel[value] }))
const severityItems = SEVERITIES.map((value) => ({ value, label: severityLabel[value] }))

/** Props for `SourceFields`. */
export interface SourceFieldsProps {
  form: SourceForm
  /** A new source: slug and type are editable, and the slug follows the name until edited. */
  create: boolean
  /** Slug of the team, for the link to its event schemas. */
  teamSlug: string
}

/** The fields of the source dialog: name, slug, type, severity mapping and enabled. */
export function SourceFields({ form, create, teamSlug }: SourceFieldsProps) {
  const { errors } = form.formState
  const [slugEdited, setSlugEdited] = useState(false)
  const nameField = form.register('name', {
    onChange: (event: { target: { value: string } }) => {
      if (create && !slugEdited) form.setValue('slug', slugify(event.target.value))
    },
  })
  const type = useWatch({ control: form.control, name: 'type' })

  return (
    <FieldGroup>
      <Field invalid={errors.name !== undefined}>
        <FieldLabel>Name</FieldLabel>
        <Input autoComplete="off" autoFocus {...nameField} />
        {errors.name?.message !== undefined && <FieldError>{errors.name.message}</FieldError>}
      </Field>
      {create && (
        <>
          <Field invalid={errors.slug !== undefined}>
            <FieldLabel>Slug</FieldLabel>
            <Input
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-[13px]"
              {...form.register('slug', { onChange: () => setSlugEdited(true) })}
            />
            <FieldDescription>Part of the ingest URL, e.g. /ingest/payments-webhook. It can't be changed later.</FieldDescription>
            {errors.slug?.message !== undefined && <FieldError>{errors.slug.message}</FieldError>}
          </Field>
          <Controller
            control={form.control}
            name="type"
            render={({ field, fieldState }) => (
              <Field invalid={fieldState.error !== undefined}>
                <FieldLabel>Type</FieldLabel>
                <Select items={typeItems} value={field.value} onValueChange={(next) => next !== null && field.onChange(next)}>
                  <SelectTrigger className="w-56">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {typeItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>{sourceTypeHelp[type]} The type can't be changed later.</FieldDescription>
                {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
              </Field>
            )}
          />
        </>
      )}

      <p className="text-[12px]/[16px] text-muted-foreground">
        Each event is checked against the latest version of each of this team's{' '}
        <Link to="/teams/$team/schemas" params={{ team: teamSlug }} className="text-primary underline-offset-4 hover:underline">
          event schemas
        </Link>
        , and the most specific match wins.
      </p>

      <FieldSet>
        <FieldLegend>Severity</FieldLegend>
        <Field invalid={errors.severityField !== undefined}>
          <FieldLabel>Severity field</FieldLabel>
          <Input
            autoComplete="off"
            spellCheck={false}
            placeholder="level"
            className="font-mono text-[13px]"
            {...form.register('severityField')}
          />
          <FieldDescription>Optional. Leave it empty to give every event the default severity.</FieldDescription>
          {errors.severityField?.message !== undefined && <FieldError>{errors.severityField.message}</FieldError>}
        </Field>
        <SeverityMappingRows control={form.control} />
        <Controller
          control={form.control}
          name="severityDefault"
          render={({ field }) => (
            <Field>
              <FieldLabel>Default severity</FieldLabel>
              <SeveritySelect value={field.value} onChange={field.onChange} />
              <FieldDescription>For events without the field, or with a value not listed above.</FieldDescription>
            </Field>
          )}
        />
      </FieldSet>

      <Controller
        control={form.control}
        name="enabled"
        render={({ field }) => (
          <Field orientation="horizontal">
            <div className="flex flex-col gap-0.5">
              <FieldLabel>Accept events</FieldLabel>
              <FieldDescription>Turned off, the source rejects every event.</FieldDescription>
            </div>
            <Switch checked={field.value} onCheckedChange={field.onChange} />
          </Field>
        )}
      />
    </FieldGroup>
  )
}

function SeveritySelect({ value, onChange, 'aria-label': ariaLabel }: { value: Severity; onChange: (severity: Severity) => void; 'aria-label'?: string }) {
  return (
    <Select items={severityItems} value={value} onValueChange={(next) => next !== null && onChange(next)}>
      <SelectTrigger className="w-40" aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {severityItems.map((item) => {
          const Icon = severityIcon[item.value]
          return (
            <SelectItem key={item.value} value={item.value}>
              <Icon strokeWidth={1.75} aria-hidden />
              {item.label}
            </SelectItem>
          )
        })}
      </SelectContent>
    </Select>
  )
}

function SeverityMappingRows({ control }: { control: Control<SourceFormValues, unknown, SourceFormOutput> }) {
  const rows = useFieldArray({ control, name: 'severityValues' })
  return (
    <MappingList
      title="Values and their severities"
      empty="No values yet. Events get the default severity."
      count={rows.fields.length}
      onAdd={() => rows.append({ value: '', severity: 'error' })}
      control={control}
      name="severityValues"
    >
      {rows.fields.map((row, index) => (
        <li key={row.id} className="flex items-start gap-2">
          <MappingValue control={control} name={`severityValues.${index}.value`} label={`Severity value ${index + 1}`} />
          <Controller
            control={control}
            name={`severityValues.${index}.severity`}
            render={({ field }) => (
              <SeveritySelect value={field.value} onChange={field.onChange} aria-label={`Severity for value ${index + 1}`} />
            )}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon-md"
            aria-label={`Remove severity value ${index + 1}`}
            onClick={() => rows.remove(index)}
          >
            <Trash2 strokeWidth={1.75} />
          </Button>
        </li>
      ))}
    </MappingList>
  )
}

function MappingValue({
  control,
  name,
  label,
}: {
  control: Control<SourceFormValues, unknown, SourceFormOutput>
  name: `severityValues.${number}.value`
  label: string
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field className="w-40 shrink-0" invalid={fieldState.error !== undefined}>
          <Input
            aria-label={label}
            autoComplete="off"
            spellCheck={false}
            className="font-mono text-[13px]"
            {...field}
          />
          {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
        </Field>
      )}
    />
  )
}

interface MappingListProps {
  title: string
  /** Shown while there are no rows. */
  empty: string
  count: number
  onAdd: () => void
  control: Control<SourceFormValues, unknown, SourceFormOutput>
  name: 'severityValues'
  children: ReactNode
}

function MappingList({ title, empty, count, onAdd, control, name, children }: MappingListProps) {
  const { errors } = useFormState({ control, name })
  const message = errors[name]?.root?.message ?? errors[name]?.message
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[12px]/[16px] font-medium text-muted-foreground">{title}</h3>
      {count === 0 ? (
        <p className="text-[12px]/[16px] text-muted-foreground">{empty}</p>
      ) : (
        <ul aria-label={title} className="flex flex-col gap-2">
          {children}
        </ul>
      )}
      {message !== undefined && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {message}
        </p>
      )}
      <div>
        <Button type="button" variant="secondary" size="sm" onClick={onAdd}>
          <Plus strokeWidth={1.75} aria-hidden />
          Add value
        </Button>
      </div>
    </div>
  )
}
