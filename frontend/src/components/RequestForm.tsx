import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'

export interface SubmitPayload {
  request: string
  energy: 'Low' | 'Medium' | 'High'
  approve: boolean
}

interface Props {
  value: string
  onChange: (value: string) => void
  disabled: boolean
  onSubmit: (payload: SubmitPayload) => void
}

export function RequestForm({ value, onChange, disabled, onSubmit }: Props) {
  const [energy, setEnergy] = useState<'Low' | 'Medium' | 'High'>('Medium')
  const [approve, setApprove] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim() || disabled) return
    onSubmit({ request: value.trim(), energy, approve })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        rows={3}
        placeholder="e.g. Research the top 3 CRM tools, write a comparison report, and draft an email to my manager"
        className="w-full resize-none rounded-xl border border-cyan-500/15 bg-white/[0.03] px-4 py-3.5 text-sm text-gray-100 backdrop-blur-sm placeholder:text-gray-500 transition focus:border-cyan-400/50 focus:outline-none focus:ring-4 focus:ring-cyan-400/10 focus:shadow-[0_0_24px_rgba(34,211,238,0.12)] disabled:opacity-60"
      />

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-400">
          Energy
          <select
            value={energy}
            onChange={(e) => setEnergy(e.target.value as typeof energy)}
            disabled={disabled}
            className="rounded-lg border border-cyan-500/15 bg-white/[0.03] px-2.5 py-1.5 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 disabled:opacity-60"
          >
            <option className="bg-gray-950">Low</option>
            <option className="bg-gray-950">Medium</option>
            <option className="bg-gray-950">High</option>
          </select>
        </label>

        <label className="flex items-center gap-2 text-sm text-gray-400">
          <input
            type="checkbox"
            checked={approve}
            onChange={(e) => setApprove(e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 rounded border-cyan-500/30 bg-transparent text-cyan-500 focus:ring-cyan-400/40"
          />
          Allow real-world actions (e.g. actually send email)
        </label>

        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-violet-600 px-4 py-2.5 text-sm font-medium text-white shadow-[0_0_16px_rgba(34,211,238,0.35)] transition hover:shadow-[0_0_24px_rgba(34,211,238,0.55)] disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
        >
          {disabled ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Run AgentOS
        </button>
      </div>
    </form>
  )
}
