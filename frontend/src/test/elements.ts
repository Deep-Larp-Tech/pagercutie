/** The element at `index` (negative counts from the end); fails the test when there is none, so callers need no cast. */
export function nth(elements: readonly HTMLElement[], index: number): HTMLElement {
  const element = elements.at(index)
  if (element === undefined) throw new Error(`Expected an element at index ${index}, found ${elements.length} elements`)
  return element
}
