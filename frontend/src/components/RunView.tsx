import { AlertCircle, CheckCircle2, ListChecks } from 'lucide-react'
import { ApprovalPanel } from './ApprovalPanel'
import { MetricsBar } from './MetricsBar'
import { StepCard, type StepViewModel } from './StepCard'
import type { ExecuteResult, PlanStep } from '../types'
import type { RunState } from '../runReducer'

interface Props {
  state: RunState
  onExecuted: (results: ExecuteResult[]) => void
}

function stepViewModels(plan: PlanStep[], steps: RunState['steps']): StepViewModel[] {
  return plan.map((planStep, index) => {
    const live = steps[index]
    return {
      index,
      agent: live?.agent ?? planStep.agent,
      instruction: live?.instruction ?? planStep.instruction,
      status: live?.status ?? 'queued',
      output: live?.output,
    }
  })
}

export function RunView({ state, onExecuted }: Props) {
  if (state.phase === 'idle') return null

  const steps = stepViewModels(state.plan, state.steps)

  return (
    <div className="space-y-4">
      {state.plan.length > 0 && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
            <ListChecks className="h-4 w-4" />
            Plan
          </h3>
          <div className="space-y-2">
            {steps.map((step) => (
              <StepCard key={step.index} step={step} />
            ))}
          </div>
        </div>
      )}

      {state.verify && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            state.verify.satisfied
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300'
              : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300'
          }`}
        >
          {state.verify.satisfied
            ? '✔ Verifier: output satisfies the request'
            : `✎ Verifier requested a revision: ${state.verify.feedback}`}
        </div>
      )}

      {state.pendingActions.length > 0 && (
        <ApprovalPanel actions={state.pendingActions} onExecuted={onExecuted} />
      )}

      {state.executeResults && (
        <div className="space-y-2">
          {state.executeResults.map((r, i) => (
            <div
              key={i}
              className="rounded-lg border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/30 p-3"
            >
              <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                Executed: {r.tool}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-emerald-900 dark:text-emerald-200">
                {r.result}
              </p>
            </div>
          ))}
        </div>
      )}

      {state.errorMessage && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          {state.errorMessage}
        </div>
      )}

      {state.finalOutput != null && state.phase === 'done' && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            Result
          </h3>
          <p className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
            {state.finalOutput}
          </p>
        </div>
      )}

      {state.metrics && <MetricsBar metrics={state.metrics} />}
    </div>
  )
}
