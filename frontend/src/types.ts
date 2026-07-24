export interface AgentSpec {
  name: string
  description: string
  tools: string[]
}

export interface PlanStep {
  agent: string
  instruction: string
  depends_on: number[]
}

export type StepStatus = 'ok' | 'failed' | 'skipped'

export interface PendingAction {
  tool: string
  args: Record<string, unknown>
}

export interface MetricsPayload {
  duration_s: number
  llm_calls: number
  tool_calls: number
  tokens: number
  est_cost_usd: number
}

export type AgentEvent =
  | { type: 'plan'; steps: PlanStep[]; session_id: string }
  | { type: 'step_start'; index: number; agent: string; instruction: string }
  | {
      type: 'step_result'
      index: number
      agent: string
      output: string
      status: StepStatus
    }
  | { type: 'verify'; satisfied: boolean; feedback: string }
  | { type: 'approval_required'; actions: PendingAction[] }
  | { type: 'error'; message: string }
  | ({ type: 'metrics' } & MetricsPayload)
  | { type: 'done'; output: string; session_id: string }

export interface ExecuteResult {
  tool: string
  args: Record<string, unknown>
  result: string
}
