import type { RuntimeCapability, RuntimeEvent } from '../../api/jarvis'
import type { AgentPhase, ExecutionStep } from '../../models/chat'

export const MAX_EXECUTION_TRACE_STEPS = 96
export const MAX_TOOL_OPERATIONS = 32

export type ExecutionTraceStatus = 'running' | 'completed' | 'failed' | 'cancelled'

export interface ExecutionTrace {
  turnId: string
  steps: ExecutionStep[]
  status: ExecutionTraceStatus
  toolStartedCount: number
}

const phaseLabels: Record<AgentPhase, string> = {
  thinking: 'Thinking',
  searching: 'Searching',
  reviewing: 'Reviewing result',
  computing: 'Computing',
  composing: 'Composing',
}

export const capabilityLabels: Record<RuntimeCapability, string> = {
  search_personal_resources: 'Search personal resources',
  read_personal_resource: 'Read resource',
  review_personal_resources: 'Review personal resources',
  run_python: 'Run Python',
  write_workspace: 'Write workspace file',
  read_workspace: 'Read workspace file',
  manage_workspace: 'Manage workspace',
  search_web: 'Search the web',
  read_web_source: 'Read web source',
  use_tool: 'Use tool',
}

export function createExecutionTrace(turnId: string): ExecutionTrace {
  return { turnId, steps: [], status: 'running', toolStartedCount: 0 }
}

function finishCurrent(steps: ExecutionStep[]): ExecutionStep[] {
  return steps.map((step) => step.state === 'current' ? { ...step, state: 'completed' } : step)
}

function bounded(steps: ExecutionStep[]): ExecutionStep[] {
  return steps.length <= MAX_EXECUTION_TRACE_STEPS ? steps : steps.slice(-MAX_EXECUTION_TRACE_STEPS)
}

function appendCurrent(trace: ExecutionTrace, step: ExecutionStep): ExecutionTrace {
  return { ...trace, steps: bounded([...finishCurrent(trace.steps), step]) }
}

function terminal(trace: ExecutionTrace, status: Exclude<ExecutionTraceStatus, 'running'>): ExecutionTrace {
  const state: ExecutionStep['state'] = status === 'completed' ? 'completed' : status
  const label = status === 'completed' ? 'Completed' : status === 'failed' ? 'Failed' : 'Cancelled'
  const existing = trace.steps.map((step) => step.state === 'current' ? { ...step, state } : step)
  return {
    ...trace,
    status,
    steps: bounded([...existing, { id: `terminal:${status}`, label, detail: status === 'completed' ? 'Finished' : label, state }]),
  }
}

export function reduceExecutionTrace(current: ExecutionTrace | null, event: RuntimeEvent): ExecutionTrace {
  let trace = current?.turnId === event.turn_id ? current : createExecutionTrace(event.turn_id)
  if (trace.status !== 'running') return trace

  if (event.type === 'turn.started') {
    if (trace.steps.some((step) => step.id === 'turn:started')) return trace
    return appendCurrent(trace, { id: 'turn:started', label: 'Started', detail: 'Turn started', state: 'current' })
  }
  if (event.type === 'phase.changed' && event.phase) {
    const id = `phase:${event.phase}`
    const last = trace.steps.at(-1)
    if (last?.id?.startsWith(`${id}:`) && last.state === 'current') return trace
    return appendCurrent(trace, { id: `${id}:${event.sequence}`, label: phaseLabels[event.phase], detail: 'In progress', state: 'current' })
  }
  if (event.type === 'tool.started' && event.operation_id && event.capability) {
    if (trace.toolStartedCount >= MAX_TOOL_OPERATIONS || trace.steps.some((step) => step.id === `tool:${event.operation_id}`)) return trace
    trace = appendCurrent(trace, {
      id: `tool:${event.operation_id}`,
      label: capabilityLabels[event.capability],
      detail: 'Running',
      state: 'current',
    })
    return { ...trace, toolStartedCount: trace.toolStartedCount + 1 }
  }
  if (event.type === 'tool.completed' && event.operation_id) {
    return {
      ...trace,
      steps: trace.steps.map((step) => step.id === `tool:${event.operation_id}`
        ? { ...step, detail: event.duration_ms === undefined ? 'Finished' : `Finished · ${event.duration_ms} ms`, state: 'completed' }
        : step),
    }
  }
  if (event.type === 'turn.completed') return terminal(trace, 'completed')
  if (event.type === 'turn.failed') return terminal(trace, 'failed')
  if (event.type === 'turn.cancelled') return terminal(trace, 'cancelled')
  return trace
}
