import { useState } from 'react'
import { AlertTriangle, Loader2, ShieldCheck } from 'lucide-react'
import { ApiError, executeApproved } from '../api'
import type { ExecuteResult, PendingAction } from '../types'

interface Props {
  actions: PendingAction[]
  onExecuted: (results: ExecuteResult[]) => void
}

export function ApprovalPanel({ actions, onExecuted }: Props) {
  const [executing, setExecuting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleApprove() {
    setExecuting(true)
    setError(null)
    try {
      const results = await executeApproved(actions)
      onExecuted(results)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to execute.')
    } finally {
      setExecuting(false)
    }
  }

  return (
    <div className="rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 shrink-0 text-amber-500 mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-amber-900 dark:text-amber-200">
            {actions.length} action{actions.length > 1 ? 's' : ''} awaiting approval
          </h3>
          <p className="mt-1 text-sm text-amber-800/80 dark:text-amber-300/80">
            These irreversible actions were prepared but not executed. Review them,
            then approve to run <em>exactly</em> what was previewed - never a
            re-generated version.
          </p>
          <ul className="mt-3 space-y-2">
            {actions.map((action, i) => (
              <li
                key={i}
                className="rounded border border-amber-200 dark:border-amber-900 bg-white dark:bg-gray-950 p-3 font-mono text-xs"
              >
                <span className="font-semibold text-amber-700 dark:text-amber-400">
                  {action.tool}
                </span>
                <pre className="mt-1 overflow-x-auto text-gray-600 dark:text-gray-400">
                  {JSON.stringify(action.args, null, 2)}
                </pre>
              </li>
            ))}
          </ul>
          {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
          <button
            type="button"
            onClick={handleApprove}
            disabled={executing}
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-60"
          >
            {executing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldCheck className="h-4 w-4" />
            )}
            Approve &amp; execute exactly what was previewed
          </button>
        </div>
      </div>
    </div>
  )
}
