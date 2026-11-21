import { Badge } from '@/components/ui/badge'
import { constraintLabel, type FieldNode } from '@/lib/json-schema-tree'

/** Props for `FieldTree`. */
export interface FieldTreeProps {
  /** Fields from `fieldTree(jsonSchema)`. */
  nodes: readonly FieldNode[]
  /** Accessible name of the list. */
  label?: string
}

/**
 * The fields an event schema describes (`SCH-3`), nested: name and path in Geist Mono, types, whether the field is
 * required, value constraints in plain words, and a note on recursive or external `$ref`s.
 */
export function FieldTree({ nodes, label = 'Fields' }: FieldTreeProps) {
  if (nodes.length === 0) {
    return <p className="text-muted-foreground">No fields yet. List them under properties in the JSON Schema.</p>
  }
  return (
    <ul aria-label={label} className="flex flex-col gap-2">
      {nodes.map((node) => (
        <FieldItem key={`${node.path}/${node.name}`} node={node} />
      ))}
    </ul>
  )
}

function FieldItem({ node }: { node: FieldNode }) {
  const notes = node.constraints.map(constraintLabel)
  return (
    <li className="flex flex-col gap-1" data-path={node.path}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono text-[13px]/[20px] font-medium" title={node.path === '' ? undefined : node.path}>
          {node.name}
        </span>
        {node.types.map((type) => (
          <Badge key={type} className="font-mono">
            {type}
          </Badge>
        ))}
        {node.required && <span className="text-[12px]/[16px] font-medium text-primary">required</span>}
        {notes.length > 0 && <span className="text-[12px]/[16px] text-muted-foreground">{notes.join(' · ')}</span>}
      </div>
      {node.description !== null && <p className="text-[12px]/[16px] text-muted-foreground">{node.description}</p>}
      {node.recursive && (
        <p className="text-[12px]/[16px] text-muted-foreground">
          Repeats <span className="font-mono">{node.ref}</span> inside itself.
        </p>
      )}
      {node.unresolved && (
        <p className="text-[12px]/[16px] text-muted-foreground">
          Defined outside this schema at <span className="font-mono">{node.ref}</span>.
        </p>
      )}
      {node.children.length > 0 && (
        <div className="flex flex-col gap-1 border-l pl-4">
          {node.combinator !== null && (
            <span className="text-[12px]/[16px] font-medium text-muted-foreground">{node.combinator}</span>
          )}
          <FieldTree nodes={node.children} label={`Fields of ${node.path === '' ? node.name : node.path}`} />
        </div>
      )}
    </li>
  )
}
