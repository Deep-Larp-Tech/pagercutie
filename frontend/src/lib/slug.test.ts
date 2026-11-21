import { describe, expect, test } from 'vitest'
import { createTeamBodySlugRegExp } from '@/api/generated/teams/teams.zod'
import { slugify } from './slug'

describe('slugify', () => {
  test.each([
    ['Payments', 'payments'],
    ['Card  payments & refunds', 'card-payments-refunds'],
    ['Účty a platby', 'ucty-a-platby'],
    ['  --Team 42--  ', 'team-42'],
    ['!!!', ''],
  ])('%j becomes %j', (name, slug) => {
    expect(slugify(name)).toBe(slug)
  })

  test('cuts at 50 characters without leaving a trailing hyphen', () => {
    const slug = slugify(`${'a'.repeat(49)} b`)
    expect(slug).toBe('a'.repeat(49))
    expect(slug).toMatch(createTeamBodySlugRegExp)
  })
})
