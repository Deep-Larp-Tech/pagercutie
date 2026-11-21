import { useEffect, useSyncExternalStore, type ComponentType } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  applyTheme,
  darkSchemeQuery,
  readThemeChoice,
  storeThemeChoice,
  subscribeThemeChoice,
  themeChoices,
  type ThemeChoice,
} from '@/lib/theme'

const themeChoiceLabel = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
} as const satisfies Record<ThemeChoice, string>

const themeChoiceIcon = {
  light: Sun,
  dark: Moon,
  system: Monitor,
} as const satisfies Record<ThemeChoice, ComponentType<{ strokeWidth: number; 'aria-hidden': boolean }>>

/** Light, Dark and System segmented control; stores the choice and follows the OS while System is picked (DESIGN.md §3). */
export function ThemeToggle({ className }: { className?: string }) {
  // The command menu changes the theme too, so the toggle follows the store instead of keeping its own state.
  const choice = useSyncExternalStore(subscribeThemeChoice, readThemeChoice)

  useEffect(() => {
    applyTheme(choice)
    if (choice !== 'system') return
    const query = matchMedia(darkSchemeQuery)
    const onChange = () => applyTheme('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [choice])

  return (
    <ToggleGroup<ThemeChoice>
      aria-label="Theme"
      className={cn('w-full', className)}
      value={[choice]}
      onValueChange={([next]) => {
        if (next === undefined) return
        storeThemeChoice(next)
      }}
    >
      {themeChoices.map((option) => {
        const Icon = themeChoiceIcon[option]
        return (
          <ToggleGroupItem key={option} value={option} className="flex-1 px-1.5">
            <Icon strokeWidth={1.75} aria-hidden />
            {themeChoiceLabel[option]}
          </ToggleGroupItem>
        )
      })}
    </ToggleGroup>
  )
}
