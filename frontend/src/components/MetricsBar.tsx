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
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-cyan-500/10 bg-white/[0.02] px-4 py-2.5 font-mono text-xs text-gray-400 backdrop-blur-sm">
      {items.map(({ icon: Icon, label }) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5 text-violet-400" />
          {label}
        </span>
      ))}
    </div>
  )
}
