import { Bot, Settings, Wifi, WifiOff } from 'lucide-react'
import type { AgentSpec } from '../types'

interface Props {
  agents: AgentSpec[]
  healthy: boolean | null
  onOpenSettings: () => void
}

export function Sidebar({ agents, healthy, onOpenSettings }: Props) {
  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950">
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="text-xl">🧠</span>
          <h1 className="font-semibold text-gray-900 dark:text-gray-100">AgentOS</h1>
        </div>
        <button
          type="button"
          onClick={onOpenSettings}
          className="rounded-md p-1.5 text-gray-400 hover:bg-gray-200 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          aria-label="Settings"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Registered agents
        </h2>
        <ul className="space-y-2">
          {agents.map((agent) => (
            <li
              key={agent.name}
              className="rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3"
            >
              <div className="flex items-center gap-2">
                <Bot className="h-3.5 w-3.5 shrink-0 text-gray-400" />
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

      <div className="flex items-center gap-2 border-t border-gray-200 dark:border-gray-800 px-4 py-3 text-xs">
        {healthy === null ? (
          <span className="text-gray-400">Checking connection…</span>
        ) : healthy ? (
          <>
            <Wifi className="h-3.5 w-3.5 text-emerald-500" />
            <span className="text-gray-500 dark:text-gray-400">API connected</span>
          </>
        ) : (
          <>
            <WifiOff className="h-3.5 w-3.5 text-red-500" />
            <span className="text-red-500">API unreachable</span>
          </>
        )}
      </div>
    </aside>
  )
}
