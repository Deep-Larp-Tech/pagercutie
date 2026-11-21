import { useEffect, useSyncExternalStore } from 'react'
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
      className={className}
      value={[choice]}
      onValueChange={([next]) => {
        if (next === undefined) return
        storeThemeChoice(next)
      }}
    >
      {themeChoices.map((option) => (
        <ToggleGroupItem key={option} value={option}>
          {themeChoiceLabel[option]}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
