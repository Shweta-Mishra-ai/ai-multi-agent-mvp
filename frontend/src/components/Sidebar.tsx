import { Bot, Settings, Wifi, WifiOff } from 'lucide-react'
import type { AgentSpec } from '../types'

interface Props {
  agents: AgentSpec[]
  healthy: boolean | null
  onOpenSettings: () => void
}

export function Sidebar({ agents, healthy, onOpenSettings }: Props) {
  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-gray-200/80 dark:border-gray-800 bg-white/70 dark:bg-gray-950/70 backdrop-blur-sm">
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-base shadow-sm shadow-indigo-500/30">
            🧠
          </span>
          <h1 className="font-semibold tracking-tight text-gray-900 dark:text-gray-100">
            AgentOS
          </h1>
        </div>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          aria-label="Settings"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-600">
          Registered agents
        </h2>
        <ul className="space-y-2">
          {agents.map((agent) => (
            <li
              key={agent.name}
              className="group rounded-xl border border-gray-200/80 dark:border-gray-800 bg-white dark:bg-gray-900 p-3 shadow-sm transition hover:border-indigo-200 hover:shadow-md dark:hover:border-indigo-900"
            >
              <div className="flex items-center gap-2">
                <Bot className="h-3.5 w-3.5 shrink-0 text-indigo-400 dark:text-indigo-500" />
                <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
                  {agent.name}
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {agent.description}
              </p>
              {agent.tools.length > 0 && (
                <p className="mt-1.5 truncate text-[11px] font-mono text-gray-400 dark:text-gray-600">
                  {agent.tools.join(', ')}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-gray-200/80 dark:border-gray-800 px-4 py-3">
        {healthy === null ? (
          <span className="text-xs text-gray-400">Checking connection…</span>
        ) : healthy ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
            <Wifi className="h-3.5 w-3.5" />
            API connected
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 dark:bg-red-950/40 px-2.5 py-1 text-xs font-medium text-red-600 dark:text-red-400">
            <WifiOff className="h-3.5 w-3.5" />
            API unreachable
          </span>
        )}
      </div>
    </aside>
  )
}
