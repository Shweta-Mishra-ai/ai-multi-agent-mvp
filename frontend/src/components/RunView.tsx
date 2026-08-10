import { AlertCircle, CheckCircle2, ListChecks, PenLine, Volume2, VolumeX } from 'lucide-react'
import { ApprovalPanel } from './ApprovalPanel'
import { MetricsBar } from './MetricsBar'
import { StepCard, type StepViewModel } from './StepCard'
import { useSpeechSynthesis } from '../hooks/useSpeechSynthesis'
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
  const tts = useSpeechSynthesis()

  if (state.phase === 'idle') return null

  const steps = stepViewModels(state.plan, state.steps)

  return (
    <div className="space-y-4">
      {state.plan.length > 0 && (
        <div className="rounded-xl border border-cyan-500/10 bg-white/[0.02] p-4 backdrop-blur-sm">
          <h3 className="mb-3 flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-cyan-100/50">
            <ListChecks className="h-4 w-4 text-cyan-400" />
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
          className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm backdrop-blur-sm ${
            state.verify.satisfied
              ? 'border-emerald-400/20 bg-emerald-500/[0.06] text-emerald-300'
              : 'border-amber-400/20 bg-amber-500/[0.06] text-amber-300'
          }`}
        >
          {state.verify.satisfied ? (
            <>
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
              Verifier: output satisfies the request
            </>
          ) : (
            <>
              <PenLine className="h-4 w-4 shrink-0 mt-0.5" />
              Verifier requested a revision: {state.verify.feedback}
            </>
          )}
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
              className="rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] p-3 backdrop-blur-sm"
            >
              <p className="font-mono text-xs font-semibold text-emerald-300">
                Executed: {r.tool}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-emerald-100/90">
                {r.result}
              </p>
            </div>
          ))}
        </div>
      )}

      {state.errorMessage && (
        <div className="flex items-start gap-2 rounded-xl border border-red-400/20 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300 backdrop-blur-sm">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          {state.errorMessage}
        </div>
      )}

      {state.finalOutput != null && state.phase === 'done' && (
        <div className="rounded-xl border border-cyan-500/10 bg-white/[0.02] p-4 backdrop-blur-sm">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-cyan-100/50">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              Result
            </h3>
            <button
              type="button"
              onClick={() =>
                tts.speaking ? tts.stop() : tts.speak(state.finalOutput ?? '')
              }
              aria-label={tts.speaking ? 'Stop reading aloud' : 'Read result aloud'}
              title={tts.speaking ? 'Stop reading aloud' : 'Read aloud'}
              className={`flex h-6 w-6 items-center justify-center rounded-full transition ${
                tts.speaking
                  ? 'text-cyan-300 animate-glow-pulse'
                  : 'text-gray-500 hover:text-cyan-300'
              }`}
            >
              {tts.speaking ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
            </button>
          </div>
          <p className="whitespace-pre-wrap text-sm text-gray-200">
            {state.finalOutput}
          </p>
        </div>
      )}

      {state.metrics && <MetricsBar metrics={state.metrics} />}
    </div>
  )
}
