import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { StatusPill } from './StatusPill'
import type { StepStatus } from '../types'

export interface StepViewModel {
  index: number
  agent: string
  instruction: string
  status: StepStatus | 'running' | 'queued'
  output?: string
}

export function StepCard({ step }: { step: StepViewModel }) {
  const [open, setOpen] = useState(step.status !== 'queued')
  const hasOutput = step.output != null && step.output !== ''

  return (
    <div className="rounded-xl border border-cyan-500/10 bg-white/[0.02] backdrop-blur-sm overflow-hidden transition hover:border-cyan-400/20">
      <button
        type="button"
        onClick={() => hasOutput && setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.03] disabled:cursor-default"
        disabled={!hasOutput}
      >
        <div className="flex min-w-0 items-center gap-3">
          {hasOutput ? (
            open ? (
              <ChevronDown className="h-4 w-4 shrink-0 text-gray-500" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0 text-gray-500" />
            )
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <span className="shrink-0 rounded-md border border-cyan-400/20 bg-cyan-500/10 px-2 py-0.5 font-mono text-xs font-medium text-cyan-300">
            {step.index + 1}
          </span>
          <span className="shrink-0 font-semibold text-gray-100">
            {step.agent}
          </span>
          <span className="truncate text-sm text-gray-400">
            {step.instruction}
          </span>
        </div>
        <StatusPill status={step.status} />
      </button>
      {open && hasOutput && (
        <div className="border-t border-cyan-500/10 bg-black/20 px-4 py-3">
          <p className="whitespace-pre-wrap text-sm text-gray-300">
            {step.output}
          </p>
        </div>
      )}
    </div>
  )
}
