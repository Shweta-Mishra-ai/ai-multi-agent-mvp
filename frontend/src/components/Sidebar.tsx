import { Bot, ChevronRight, Settings, WifiOff } from 'lucide-react'
import type { AgentSpec } from '../types'

interface Props {
  agents: AgentSpec[]
  healthy: boolean | null
  onOpenSettings: () => void
}

export function Sidebar({ agents, healthy, onOpenSettings }: Props) {
  return (
    <aside className="relative z-10 flex w-72 shrink-0 flex-col border-r border-cyan-500/10 bg-black/30 backdrop-blur-md">
      <div className="flex items-center justify-between px-4 py-4">
        <h1 className="bg-gradient-to-r from-cyan-200 to-violet-300 bg-clip-text font-mono text-sm font-semibold tracking-widest text-transparent">
          AGENTOS
        </h1>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-lg p-1.5 text-cyan-100/40 transition hover:bg-white/5 hover:text-cyan-200"
          aria-label="Settings"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <h2 className="mb-2 font-mono text-xs uppercase tracking-widest text-cyan-100/30">
          Registered agents
        </h2>
        <ul className="space-y-1.5">
          {agents.map((agent) => (
            <li key={agent.name}>
              <details className="group rounded-xl border border-cyan-500/10 bg-white/[0.03] backdrop-blur-sm transition hover:border-cyan-400/30 open:border-cyan-400/30 open:bg-white/[0.05]">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 [&::-webkit-details-marker]:hidden">
                  <Bot className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                  <span className="font-medium text-sm text-gray-100">
                    {agent.name}
                  </span>
                  <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-gray-600 transition group-open:rotate-90" />
                </summary>
                <div className="px-3 pb-3">
                  <p className="text-xs text-gray-400">
                    {agent.description}
                  </p>
                  {agent.tools.length > 0 && (
                    <p className="mt-1.5 text-[11px] font-mono text-violet-300/50">
                      {agent.tools.join(', ')}
                    </p>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-cyan-500/10 px-4 py-3">
        {healthy === null ? (
          <span className="font-mono text-xs text-gray-500">checking connection…</span>
        ) : healthy ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-500/10 px-2.5 py-1 font-mono text-xs font-medium text-emerald-300">
            <span className="relative flex h-2 w-2">
              <span className="animate-glow-pulse absolute inline-flex h-full w-full rounded-full bg-emerald-400" />
            </span>
            api connected
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-red-400/20 bg-red-500/10 px-2.5 py-1 font-mono text-xs font-medium text-red-300">
            <WifiOff className="h-3.5 w-3.5" />
            api unreachable
          </span>
        )}
      </div>
    </aside>
  )
}
