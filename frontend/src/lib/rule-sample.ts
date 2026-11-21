import type { Severity } from '@/api/generated/model'

/** The sample event the author tests against, as typed. Kept by the builder; never saved. */
export interface SampleEvent {
  /** The event's payload as JSON text. */
  payload: string
  source: string
  severity: Severity
}

/** The sample's payload, or why it is not a JSON object. */
export function parseSample(text: string): { ok: true; payload: { [key: string]: unknown } } | { ok: false; message: string } {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (error) {
    return { ok: false, message: `The sample isn't valid JSON: ${error instanceof Error ? error.message : String(error)}` }
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { ok: false, message: 'The sample must be a JSON object, like {"type": "WORKFLOW_FAILED"}.' }
  }
  return { ok: true, payload: Object.fromEntries(Object.entries(value)) }
}

/** The normalised event a sample stands for (SPEC §4.2), for templates and the preview; `null` while it is invalid. */
export function sampleEvent(sample: SampleEvent, schemaId: string | null): unknown {
  const parsed = parseSample(sample.payload)
  return parsed.ok ? { source: sample.source, severity: sample.severity, schema_id: schemaId, payload: parsed.payload } : null
}
