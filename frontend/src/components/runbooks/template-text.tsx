import { templateParts } from '@/lib/runbooks'
import { cn } from '@/lib/utils'

/** Text with its `{{field.path}}` placeholders set in Geist Mono on a muted chip (DESIGN.md §6). */
export function TemplateText({ text, className }: { text: string; className?: string }) {
  return (
    <span className={cn('break-words', className)}>
      {templateParts(text).map((part, index) =>
        part.placeholder ? (
          <code
            key={index}
            data-placeholder
            className="rounded-sm bg-muted px-1 font-mono text-[13px]/[20px] font-[450] text-foreground ring-1 ring-border"
          >
            {part.text}
          </code>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </span>
  )
}
