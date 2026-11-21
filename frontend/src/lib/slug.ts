import { createTeamBodySlugMax } from '@/api/generated/teams/teams.zod'

/**
 * A slug for `name` that matches the slug pattern (DOMAIN.md §1): lower case ASCII letters and digits joined by
 * single hyphens, at most `createTeamBodySlugMax` characters. Accents are dropped (`Účty` becomes `ucty`); the
 * result is empty when `name` has no letters or digits.
 */
export function slugify(name: string): string {
  return name
    .normalize('NFKD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+/, '')
    .slice(0, createTeamBodySlugMax)
    .replace(/-+$/, '')
}
