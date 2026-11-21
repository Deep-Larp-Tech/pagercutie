import { describe, expect, test } from 'vitest'
import { OFFLINE, pagedList, type PageResult } from './pagination'

const items = (...values: number[]): PageResult<number> => ({ kind: 'items', items: values })

describe('pagedList', () => {
  test('is loading until the first page answers, or failed when it got no answer', () => {
    expect(pagedList<number>(undefined, false)).toEqual({ kind: 'loading' })
    expect(pagedList<number>(undefined, true)).toEqual({ kind: 'failed', message: OFFLINE })
  })

  test('a failed first page fails the list; a silent one keeps it loading', () => {
    expect(pagedList([{ kind: 'failed', message: 'No' }], false)).toEqual({ kind: 'failed', message: 'No' })
    expect(pagedList<number>([{ kind: 'silent' }], false)).toEqual({ kind: 'loading' })
  })

  test('joins the items of every page in order', () => {
    expect(pagedList([items(1, 2), items(3)], false)).toEqual({ kind: 'listed', items: [1, 2, 3], moreError: null })
  })

  test('a failed later page keeps the items and reports why', () => {
    expect(pagedList([items(1), { kind: 'failed', message: 'No' }], false)).toEqual({
      kind: 'listed',
      items: [1],
      moreError: 'No',
    })
    expect(pagedList([items(1)], true)).toEqual({ kind: 'listed', items: [1], moreError: OFFLINE })
  })
})
