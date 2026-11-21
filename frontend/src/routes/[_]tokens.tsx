// Temporary token preview for reviewing DESIGN.md by eye; removed in chunk 3.
import { useEffect, useState, type ReactNode } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { Colour, Severity } from '@/api/generated/model'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { alertColourClass, defaultColour, severityIcon, severityLabel } from '@/lib/severity'
import { cn } from '@/lib/utils'
import { BuildingBlocks } from './-tokens/building-blocks'

export const Route = createFileRoute('/_tokens')({
  component: TokensPage,
})

type ThemeChoice = 'light' | 'dark' | 'system'

const THEME_KEY = 'theme'
const themeChoices = ['light', 'dark', 'system'] as const satisfies readonly ThemeChoice[]
const themeChoiceLabel = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
} as const satisfies Record<ThemeChoice, string>

const darkQuery = '(prefers-color-scheme: dark)'

function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === 'light' || value === 'dark' || value === 'system'
}

function readThemeChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return isThemeChoice(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

function applyTheme(choice: ThemeChoice) {
  const theme = choice === 'system' ? (matchMedia(darkQuery).matches ? 'dark' : 'light') : choice
  const root = document.documentElement
  if (root.dataset.theme === theme) return
  const update = () => {
    root.dataset.theme = theme
    root.style.colorScheme = theme
  }
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
  if (typeof document.startViewTransition === 'function' && !reducedMotion) {
    document.startViewTransition(update)
  } else {
    update()
  }
}

const chromeTokens = [
  ['background', 'bg-background'],
  ['foreground', 'bg-foreground'],
  ['card', 'bg-card'],
  ['popover', 'bg-popover'],
  ['primary', 'bg-primary'],
  ['primary-foreground', 'bg-primary-foreground'],
  ['secondary / muted', 'bg-muted'],
  ['muted-foreground', 'bg-muted-foreground'],
  ['accent', 'bg-accent'],
  ['border', 'bg-border'],
  ['input', 'bg-input'],
  ['ring', 'bg-ring'],
  ['destructive', 'bg-destructive'],
  ['destructive-foreground', 'bg-destructive-foreground'],
] as const

const severityOrder = [
  Severity.critical,
  Severity.error,
  Severity.warn,
  Severity.info,
  Severity.debug,
] as const satisfies readonly Severity[]

const typeRoles = [
  ['Page title', 'text-[24px]/[32px] font-semibold tracking-[-0.02em]'],
  ['Section title', 'text-[18px]/[26px] font-semibold tracking-[-0.01em]'],
  ['Alert title', 'text-[15px]/[22px] font-[560]'],
  ['Body, inputs', 'text-[14px]/[20px] font-normal'],
  ['Metadata, badges', 'text-[12px]/[16px] font-medium'],
  ['Mono values', 'font-mono text-[13px]/[20px] font-[450] tabular-nums'],
] as const

const radii = [
  ['8 px, controls', 'rounded-md'],
  ['12 px, cards', 'rounded-lg'],
  ['14 px, popovers', 'rounded-xl'],
  ['full, badges', 'rounded-full'],
] as const

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[18px]/[26px] font-semibold tracking-[-0.01em]">{title}</h2>
      {children}
    </section>
  )
}

function TokensPage() {
  const [choice, setChoice] = useState<ThemeChoice>(readThemeChoice)

  useEffect(() => {
    applyTheme(choice)
    if (choice !== 'system') return
    const query = matchMedia(darkQuery)
    const onChange = () => applyTheme('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [choice])

  const pick = (next: ThemeChoice) => {
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // Storage can be unavailable (private mode); the choice still applies for this page.
    }
    setChoice(next)
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-10 p-8">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-[24px]/[32px] font-semibold tracking-[-0.02em]">Nocturne tokens</h1>
        <ToggleGroup<ThemeChoice>
          aria-label="Theme"
          value={[choice]}
          onValueChange={([next]) => {
            if (next) pick(next)
          }}
        >
          {themeChoices.map((option) => (
            <ToggleGroupItem key={option} value={option}>
              {themeChoiceLabel[option]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </header>

      <Section title="Chrome tokens">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {chromeTokens.map(([name, swatch]) => (
            <div key={name} className="flex flex-col gap-1">
              <div className={cn('h-12 rounded-md border', swatch)} />
              <span className="font-mono text-[12px]/[16px] text-muted-foreground">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Alert colours">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Object.values(Colour).map((colour) => (
            <div key={colour} className={cn('flex flex-col gap-1', alertColourClass[colour])}>
              <div className="flex h-12 overflow-hidden rounded-md border">
                <div className="flex-1 bg-c" />
                <div className="flex flex-1 items-center justify-center bg-c-tint text-c-text">
                  Aa
                </div>
              </div>
              <span className="font-mono text-[12px]/[16px] text-muted-foreground">
                {colour}: solid, tint, text
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Severity">
        <div className="flex flex-wrap gap-2">
          {severityOrder.map((severity) => {
            const Icon = severityIcon[severity]
            return (
              <span
                key={severity}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full bg-c-tint px-2 py-0.5',
                  'text-[12px]/[16px] font-medium text-c-text',
                  alertColourClass[defaultColour[severity]],
                )}
              >
                <Icon size={14} strokeWidth={1.75} aria-hidden />
                {severityLabel[severity]}
              </span>
            )
          })}
        </div>
      </Section>

      <Section title="Typography">
        <div className="flex flex-col gap-2">
          {typeRoles.map(([role, classes]) => (
            <p key={role} className={classes}>
              {role}: Settlement wf-8f21 failed at reserve-funds ×12
            </p>
          ))}
        </div>
      </Section>

      <Section title="Radii and elevation">
        <div className="flex flex-wrap gap-4">
          {radii.map(([label, radius]) => (
            <div
              key={label}
              className={cn('flex h-20 w-32 items-center justify-center border bg-card', radius)}
            >
              <span className="text-[12px]/[16px] text-muted-foreground">{label}</span>
            </div>
          ))}
          <div className="flex h-20 w-32 items-center justify-center rounded-lg bg-card shadow-card">
            <span className="text-[12px]/[16px] text-muted-foreground">Card shadow</span>
          </div>
          <div className="flex h-20 w-32 items-center justify-center rounded-xl bg-popover shadow-popover">
            <span className="text-[12px]/[16px] text-muted-foreground">Popover shadow</span>
          </div>
        </div>
      </Section>

      <Section title="Building blocks">
        <BuildingBlocks />
      </Section>
    </main>
  )
}
