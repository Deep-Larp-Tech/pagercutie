import { describe, expect, test } from 'vitest'
import { Colour, Severity } from '@/api/generated/model'
import { alertColourClass, defaultColour, severityIcon, severityLabel } from './severity'

const keysOf = (map: object) => Object.keys(map).toSorted()

describe('severity maps', () => {
  test.each([
    ['defaultColour', defaultColour],
    ['severityIcon', severityIcon],
    ['severityLabel', severityLabel],
  ])('%s has an entry for every Severity', (_name, map) => {
    expect(keysOf(map)).toEqual(Object.values(Severity).toSorted())
  })

  test('alertColourClass has an entry for every Colour', () => {
    expect(keysOf(alertColourClass)).toEqual(Object.values(Colour).toSorted())
  })

  test('defaultColour only uses known colours', () => {
    expect(Object.values(Colour)).toEqual(expect.arrayContaining(Object.values(defaultColour)))
  })
})
