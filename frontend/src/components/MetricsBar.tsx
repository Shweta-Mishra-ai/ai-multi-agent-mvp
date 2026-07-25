import { Clock, Coins, Hash, Wrench, Zap } from 'lucide-react'
import type { MetricsPayload } from '../types'

export function MetricsBar({ metrics }: { metrics: MetricsPayload }) {
  const items = [
    { icon: Clock, label: `${metrics.duration_s}s` },
    { icon: Zap, label: `${metrics.llm_calls} LLM calls` },
    { icon: Wrench, label: `${metrics.tool_calls} tool calls` },
    { icon: Hash, label: `${metrics.tokens} tokens` },
    { icon: Coins, label: `~$${metrics.est_cost_usd}` },
  ]
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg bg-gray-50 dark:bg-gray-900/50 px-4 py-2.5 text-xs text-gray-500 dark:text-gray-400">
      {items.map(({ icon: Icon, label }) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5" />
          {label}
        </span>
      ))}
    </div>
  )
}
