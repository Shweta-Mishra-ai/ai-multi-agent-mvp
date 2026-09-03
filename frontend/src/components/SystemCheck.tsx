import { useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, Stethoscope } from 'lucide-react'
import { fetchDiagnostics } from '../api'
import type { DiagnosticsReport } from '../types'

const CHECK_LABELS: Record<string, string> = {
  llm: 'Language model',
  search: 'Web search',
  storage: 'Storage',
  tools: 'Tools',
}

/**
 * Runs the real self-check on demand. Deliberately not automatic on page
 * load: it makes a live LLM call and a live search, so firing it on
 * every visit would burn quota for no reason.
 */
export function SystemCheck() {
  const [report, setReport] = useState<DiagnosticsReport | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setRunning(true)
    setError(null)
    try {
      setReport(await fetchDiagnostics())
    } catch {
      setError('Could not reach the diagnostics endpoint.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={run}
        disabled={running}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-cyan-500/20 bg-white/[0.03] px-3 py-2 font-mono text-xs text-cyan-100/70 transition hover:border-cyan-400/50 hover:text-cyan-200 disabled:opacity-50"
      >
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Stethoscope className="h-3.5 w-3.5" />
        )}
        {running ? 'checking…' : 'run system check'}
      </button>

      {error && <p className="text-xs text-red-300">{error}</p>}

      {report && (
        <ul className="space-y-1.5">
          {Object.entries(report.checks).map(([name, check]) => (
            <li
              key={name}
              className={`rounded-lg border px-2.5 py-2 ${
                check.ok
                  ? 'border-emerald-400/20 bg-emerald-500/5'
                  : 'border-red-400/25 bg-red-500/10'
              }`}
            >
              <div className="flex items-center gap-1.5">
                {check.ok ? (
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                ) : (
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-400" />
                )}
                <span className="font-mono text-xs text-gray-200">
                  {CHECK_LABELS[name] ?? name}
                </span>
              </div>
              {/* The detail is the whole point - it carries the real
                  provider error, not a generic "something went wrong". */}
              <p className="mt-1 break-words text-[11px] leading-relaxed text-gray-400">
                {check.detail}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
