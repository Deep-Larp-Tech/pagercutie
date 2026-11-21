import { ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { runbookExamples, type RunbookExample } from '@/lib/runbook-examples'

/** **Insert example** menu with the three sample runbooks from REQUIREMENTS.md §6.2 (`RUN-8`). */
export function InsertExampleMenu({ onPick }: { onPick: (example: RunbookExample) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="secondary" size="sm" />}>
        Insert example
        <ChevronDown strokeWidth={1.75} aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {runbookExamples.map((example) => (
          <DropdownMenuItem key={example.id} onClick={() => onPick(example)}>
            {example.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
