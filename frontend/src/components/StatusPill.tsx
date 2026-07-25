import { CheckCircle2, CircleDashed, Loader2, SkipForward, XCircle } from 'lucide-react'
import type { StepStatus } from '../types'

type Status = StepStatus | 'running' | 'queued'

const CONFIG: Record<
  Status,
  { icon: typeof CheckCircle2; label: string; className: string }
> = {
  queued: {
    icon: CircleDashed,
    label: 'Queued',
    className: 'text-gray-400 dark:text-gray-500',
  },
  running: {
    icon: Loader2,
    label: 'Running',
    className: 'text-blue-500 dark:text-blue-400',
  },
  ok: {
    icon: CheckCircle2,
    label: 'Done',
    className: 'text-emerald-500 dark:text-emerald-400',
  },
  failed: {
    icon: XCircle,
    label: 'Failed',
    className: 'text-red-500 dark:text-red-400',
  },
  skipped: {
    icon: SkipForward,
    label: 'Skipped',
    className: 'text-amber-500 dark:text-amber-400',
  },
}

export function StatusPill({ status }: { status: Status }) {
  const { icon: Icon, label, className } = CONFIG[status]
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${className}`}>
      <Icon className={`h-4 w-4 ${status === 'running' ? 'animate-spin' : ''}`} />
      {label}
    </span>
  )
}
