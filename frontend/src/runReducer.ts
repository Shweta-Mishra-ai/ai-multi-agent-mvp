import type { AgentEvent, ExecuteResult, MetricsPayload, PendingAction, PlanStep, StepStatus } from './types'

export type RunPhase = 'idle' | 'running' | 'awaiting-approval' | 'done' | 'error'

export interface StepViewState {
  index: number
  agent: string
  instruction: string
  status: StepStatus | 'running'
  output?: string
}

export interface RunState {
  phase: RunPhase
  sessionId: string | null
  plan: PlanStep[]
  steps: Record<number, StepViewState>
  verify: { satisfied: boolean; feedback: string } | null
  pendingActions: PendingAction[]
  errorMessage: string | null
  finalOutput: string | null
  metrics: MetricsPayload | null
  executeResults: ExecuteResult[] | null
}

export const initialRunState: RunState = {
  phase: 'idle',
  sessionId: null,
  plan: [],
  steps: {},
  verify: null,
  pendingActions: [],
  errorMessage: null,
  finalOutput: null,
  metrics: null,
  executeResults: null,
}

export type RunAction =
  | { kind: 'start' }
  | { kind: 'event'; event: AgentEvent }
  | { kind: 'submit-error'; message: string }
  | { kind: 'executed'; results: ExecuteResult[] }
  | { kind: 'execute-error'; message: string }

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.kind) {
    case 'start':
      return { ...initialRunState, phase: 'running', sessionId: state.sessionId }

    case 'submit-error':
      return { ...state, phase: 'error', errorMessage: action.message }

    case 'executed':
      return {
        ...state,
        phase: 'done',
        pendingActions: [],
        executeResults: action.results,
      }

    case 'execute-error':
      return { ...state, errorMessage: action.message }

    case 'event': {
      const event = action.event
      switch (event.type) {
        case 'plan':
          return { ...state, plan: event.steps, sessionId: event.session_id }

        case 'step_start':
          return {
            ...state,
            steps: {
              ...state.steps,
              [event.index]: {
                index: event.index,
                agent: event.agent,
                instruction: event.instruction,
                status: 'running',
              },
            },
          }

        case 'step_result':
          return {
            ...state,
            steps: {
              ...state.steps,
              [event.index]: {
                index: event.index,
                agent: event.agent,
                instruction: state.steps[event.index]?.instruction ?? '',
                status: event.status,
                output: event.output,
              },
            },
          }

        case 'verify':
          return {
            ...state,
            verify: { satisfied: event.satisfied, feedback: event.feedback },
          }

        case 'approval_required':
          return { ...state, phase: 'awaiting-approval', pendingActions: event.actions }

        case 'error':
          return { ...state, phase: 'error', errorMessage: event.message }

        case 'metrics':
          return {
            ...state,
            metrics: {
              duration_s: event.duration_s,
              llm_calls: event.llm_calls,
              tool_calls: event.tool_calls,
              tokens: event.tokens,
              est_cost_usd: event.est_cost_usd,
            },
          }

        case 'done':
          return {
            ...state,
            // A pending approval keeps its own phase until the user acts -
            // the kernel always emits `done` right after `approval_required`
            // (the "action not executed" placeholder is the final output),
            // so don't let it clear the approval banner prematurely.
            phase: state.phase === 'awaiting-approval' ? state.phase : 'done',
            finalOutput: event.output,
            sessionId: event.session_id,
          }

        default:
          return state
      }
    }

    default:
      return state
  }
}
