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
    <div className="rounded-xl border border-gray-200/80 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden transition hover:shadow-md">
      <button
        type="button"
        onClick={() => hasOutput && setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 disabled:cursor-default"
        disabled={!hasOutput}
      >
        <div className="flex min-w-0 items-center gap-3">
          {hasOutput ? (
            open ? (
              <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
            )
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <span className="shrink-0 rounded-md bg-indigo-50 dark:bg-indigo-950/50 px-2 py-0.5 text-xs font-mono font-medium text-indigo-600 dark:text-indigo-400">
            {step.index + 1}
          </span>
          <span className="shrink-0 font-semibold text-gray-900 dark:text-gray-100">
            {step.agent}
          </span>
          <span className="truncate text-sm text-gray-500 dark:text-gray-400">
            {step.instruction}
          </span>
        </div>
        <StatusPill status={step.status} />
      </button>
      {open && hasOutput && (
        <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-950/40 px-4 py-3">
          <p className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">
            {step.output}
          </p>
        </div>
      )}
    </div>
  )
}
