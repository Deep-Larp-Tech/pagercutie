// Temporary component preview for the /_tokens page; removed with it in chunk 3.
import { useState, type ReactNode } from 'react'
import { BellRing, Ellipsis, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Severity } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverDescription, PopoverTitle, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { alertColourClass, defaultColour, severityIcon, severityLabel } from '@/lib/severity'

const variants = ['primary', 'secondary', 'ghost', 'destructive'] as const
const sizes = ['sm', 'md'] as const
const severities = Object.values(Severity)
const severityItems = severities.map((value) => ({ value, label: severityLabel[value] }))

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[120px_1fr] sm:items-center">
      <span className="text-[12px]/[16px] text-muted-foreground">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

/** Every UI building block in its main states. */
export function BuildingBlocks() {
  const [severity, setSeverity] = useState<Severity | null>(Severity.error)
  const [view, setView] = useState<readonly string[]>(['open'])

  return (
    <div className="flex flex-col gap-4">
      {sizes.map((size) => (
        <Row key={size} label={`Button ${size}`}>
          {variants.map((variant) => (
            <Button key={variant} variant={variant} size={size}>
              {variant === 'destructive' ? 'Delete rule' : 'Acknowledge'}
            </Button>
          ))}
          <Button size={size} disabled>
            Disabled
          </Button>
          <Button variant="ghost" size={size === 'sm' ? 'icon-sm' : 'icon-md'} aria-label="Notify me">
            <BellRing strokeWidth={1.75} />
          </Button>
        </Row>
      ))}

      <Row label="Field">
        <div className="grid w-full max-w-xl gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel>Rule name</FieldLabel>
            <Input placeholder="Settlement failures" />
            <FieldDescription>Shown on every alert this rule raises.</FieldDescription>
          </Field>
          <Field invalid>
            <FieldLabel>Webhook URL</FieldLabel>
            <Input defaultValue="hooks.example" />
            <FieldError>Couldn't save the step. The URL must start with https://.</FieldError>
          </Field>
        </div>
      </Row>

      <Row label="Select">
        <Select items={severityItems} value={severity} onValueChange={setSeverity}>
          <SelectTrigger className="w-40" aria-label="Severity">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {severityItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select items={severityItems} disabled>
          <SelectTrigger className="w-40" aria-label="Disabled select">
            <SelectValue placeholder="Disabled" />
          </SelectTrigger>
        </Select>
      </Row>

      <Row label="Layers">
        <Dialog>
          <DialogTrigger render={<Button variant="secondary" />}>Open dialog</DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete rule</DialogTitle>
              <DialogDescription>Alerts already raised stay in the feed.</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="secondary" />}>Cancel</DialogClose>
              <DialogClose render={<Button variant="destructive" />}>Delete rule</DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <Popover>
          <PopoverTrigger render={<Button variant="secondary" />}>Open popover</PopoverTrigger>
          <PopoverContent>
            <PopoverTitle>Recipients</PopoverTitle>
            <PopoverDescription>Anna by SMS, the payments team by Slack.</PopoverDescription>
          </PopoverContent>
        </Popover>
        <Tooltip>
          <TooltipTrigger render={<Button variant="secondary" />}>Hover for tooltip</TooltipTrigger>
          <TooltipContent>Tell your team you are on it</TooltipContent>
        </Tooltip>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-md" aria-label="More actions" />}>
            <Ellipsis strokeWidth={1.75} />
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuGroup>
              <DropdownMenuLabel>Rule</DropdownMenuLabel>
              <DropdownMenuItem>Edit rule</DropdownMenuItem>
              <DropdownMenuItem>Duplicate rule</DropdownMenuItem>
              <DropdownMenuItem disabled>Test rule</DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive">
              <Trash2 strokeWidth={1.75} />
              Delete rule
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="secondary" onClick={() => toast.success('Alert acknowledged')}>
          Show toast
        </Button>
      </Row>

      <Row label="Badge">
        <Badge>3 members</Badge>
        {severities.map((value) => {
          const Icon = severityIcon[value]
          return (
            <Badge key={value} variant="tint" className={alertColourClass[defaultColour[value]]}>
              <Icon strokeWidth={1.75} aria-hidden />
              {severityLabel[value]}
            </Badge>
          )
        })}
      </Row>

      <Row label="Switch, toggle">
        <Switch defaultChecked aria-label="SMS on" />
        <Switch aria-label="SMS off" />
        <Switch disabled aria-label="Disabled" />
        <ToggleGroup value={view} onValueChange={setView} aria-label="Alert status">
          <ToggleGroupItem value="open">Open</ToggleGroupItem>
          <ToggleGroupItem value="acknowledged">Acknowledged</ToggleGroupItem>
          <ToggleGroupItem value="resolved">Resolved</ToggleGroupItem>
        </ToggleGroup>
      </Row>

      <Row label="Skeleton">
        <div className="flex w-full max-w-md flex-col gap-2 rounded-lg border p-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </Row>
    </div>
  )
}
