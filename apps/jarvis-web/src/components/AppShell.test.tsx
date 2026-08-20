import { reviewModeEnabled } from './reviewMode'

describe('production review isolation', () => {
  it('requires the dedicated review build as well as a scene', () => {
    expect(reviewModeEnabled(false, true)).toBe(false)
    expect(reviewModeEnabled(true, false)).toBe(false)
    expect(reviewModeEnabled(true, true)).toBe(true)
  })
})
