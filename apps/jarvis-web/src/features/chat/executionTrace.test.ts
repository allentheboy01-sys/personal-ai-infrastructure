import { describe, expect, it } from 'vitest'
import type { RuntimeEvent } from '../../api/jarvis'
import { MAX_EXECUTION_TRACE_STEPS, MAX_TOOL_OPERATIONS, createExecutionTrace, reduceExecutionTrace } from './executionTrace'

const event = (sequence: number, type: RuntimeEvent['type'], values: Partial<RuntimeEvent> = {}): RuntimeEvent => ({
  turn_id: 'turn-1',
  sequence,
  type,
  ...values,
})

describe('process-local execution trace reducer', () => {
  it('renders PDI and Exec lifecycle facts with calm labels', () => {
    let trace = createExecutionTrace('turn-1')
    trace = reduceExecutionTrace(trace, event(1, 'turn.started'))
    trace = reduceExecutionTrace(trace, event(2, 'phase.changed', { phase: 'searching' }))
    trace = reduceExecutionTrace(trace, event(3, 'tool.started', { operation_id: 1, category: 'pdi', capability: 'search_personal_resources' }))
    trace = reduceExecutionTrace(trace, event(4, 'tool.completed', { operation_id: 1, category: 'pdi', capability: 'search_personal_resources', duration_ms: 24 }))
    trace = reduceExecutionTrace(trace, event(5, 'tool.started', { operation_id: 2, category: 'exec', capability: 'run_python' }))
    trace = reduceExecutionTrace(trace, event(6, 'tool.completed', { operation_id: 2, category: 'exec', capability: 'run_python', duration_ms: 31 }))
    trace = reduceExecutionTrace(trace, event(7, 'turn.completed'))

    expect(trace.status).toBe('completed')
    expect(trace.toolStartedCount).toBe(2)
    expect(trace.steps.map((step) => step.label)).toEqual(['Started', 'Searching', 'Search personal resources', 'Run Python', 'Completed'])
    expect(trace.steps.find((step) => step.label === 'Search personal resources')?.detail).toBe('Finished · 24 ms')
    expect(trace.steps.at(-1)).toMatchObject({ label: 'Completed', detail: 'Finished', state: 'completed' })
  })

  it('collapses redundant consecutive phases and handles terminal outcomes', () => {
    let failed = createExecutionTrace('turn-1')
    failed = reduceExecutionTrace(failed, event(1, 'turn.started'))
    failed = reduceExecutionTrace(failed, event(2, 'phase.changed', { phase: 'thinking' }))
    failed = reduceExecutionTrace(failed, event(3, 'phase.changed', { phase: 'thinking' }))
    failed = reduceExecutionTrace(failed, event(4, 'turn.failed', { error_code: 'safe_code' }))
    expect(failed.steps.filter((step) => step.label === 'Thinking')).toHaveLength(1)
    expect(failed.steps.at(-1)).toMatchObject({ label: 'Failed', state: 'failed' })

    let cancelled = createExecutionTrace('turn-1')
    cancelled = reduceExecutionTrace(cancelled, event(1, 'turn.started'))
    cancelled = reduceExecutionTrace(cancelled, event(2, 'turn.cancelled'))
    expect(cancelled.steps.at(-1)).toMatchObject({ label: 'Cancelled', state: 'cancelled' })
  })

  it('ignores message content and unsafe extra properties', () => {
    const unsafe = event(1, 'tool.started', {
      operation_id: 1,
      category: 'other',
      capability: 'use_tool',
      delta: 'private prompt',
      error_code: 'private result',
    })
    const trace = reduceExecutionTrace(createExecutionTrace('turn-1'), unsafe)
    expect(JSON.stringify(trace)).not.toContain('private prompt')
    expect(JSON.stringify(trace)).not.toContain('private result')
    expect(trace.steps[0].label).toBe('Use tool')
  })

  it('renders only safe Web capability labels without query or URL data', () => {
    let trace = createExecutionTrace('turn-1')
    trace = reduceExecutionTrace(trace, event(1, 'tool.started', {
      operation_id: 1,
      category: 'web',
      capability: 'search_web',
      delta: 'private search query',
    }))
    trace = reduceExecutionTrace(trace, event(2, 'tool.started', {
      operation_id: 2,
      category: 'web',
      capability: 'read_web_source',
      error_code: 'https://private.example/path',
    }))
    expect(trace.steps.map((step) => step.label)).toEqual(['Search the web', 'Read web source'])
    expect(JSON.stringify(trace)).not.toContain('private search query')
    expect(JSON.stringify(trace)).not.toContain('private.example')
  })

  it('defensively bounds trace memory without affecting terminal state', () => {
    let trace = createExecutionTrace('turn-1')
    for (let sequence = 1; sequence <= 140; sequence += 1) {
      const phase = sequence % 2 ? 'thinking' : 'reviewing'
      trace = reduceExecutionTrace(trace, event(sequence, 'phase.changed', { phase }))
    }
    trace = reduceExecutionTrace(trace, event(141, 'turn.completed'))
    expect(trace.steps).toHaveLength(MAX_EXECUTION_TRACE_STEPS)
    expect(trace.status).toBe('completed')
    expect(trace.steps.at(-1)?.label).toBe('Completed')
  })

  it('defensively suppresses detailed operations after 32', () => {
    let trace = createExecutionTrace('turn-1')
    for (let operation = 1; operation <= 40; operation += 1) {
      trace = reduceExecutionTrace(trace, event(operation, 'tool.started', {
        operation_id: operation,
        category: 'other',
        capability: 'use_tool',
      }))
    }
    expect(trace.toolStartedCount).toBe(MAX_TOOL_OPERATIONS)
    expect(trace.steps.filter((step) => step.id?.startsWith('tool:'))).toHaveLength(MAX_TOOL_OPERATIONS)
  })

  it('starts a different Turn with a fresh trace', () => {
    const prior = reduceExecutionTrace(createExecutionTrace('turn-1'), event(1, 'turn.started'))
    const next = reduceExecutionTrace(prior, { turn_id: 'turn-2', sequence: 1, type: 'turn.started' })
    expect(next.turnId).toBe('turn-2')
    expect(next.steps).toHaveLength(1)
  })
})
