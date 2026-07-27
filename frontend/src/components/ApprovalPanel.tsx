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
    <div className="rounded-xl border border-amber-400/20 bg-amber-500/[0.06] p-4 backdrop-blur-sm">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-amber-200">
            {actions.length} action{actions.length > 1 ? 's' : ''} awaiting approval
          </h3>
          <p className="mt-1 text-sm text-amber-200/70">
            These irreversible actions were prepared but not executed. Review them,
            then approve to run <em>exactly</em> what was previewed - never a
            re-generated version.
          </p>
          <ul className="mt-3 space-y-2">
            {actions.map((action, i) => (
              <li
                key={i}
                className="rounded-lg border border-amber-400/20 bg-black/30 p-3 font-mono text-xs"
              >
                <span className="font-semibold text-amber-300">
                  {action.tool}
                </span>
                <pre className="mt-1 overflow-x-auto text-gray-400">
                  {JSON.stringify(action.args, null, 2)}
                </pre>
              </li>
            ))}
          </ul>
          {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
          <button
            type="button"
            onClick={handleApprove}
            disabled={executing}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white shadow-[0_0_16px_rgba(245,158,11,0.3)] transition hover:shadow-[0_0_22px_rgba(245,158,11,0.45)] disabled:opacity-60"
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
