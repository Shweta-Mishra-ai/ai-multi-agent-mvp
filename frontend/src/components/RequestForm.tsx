import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'

export interface SubmitPayload {
  request: string
  energy: 'Low' | 'Medium' | 'High'
  approve: boolean
}

interface Props {
  disabled: boolean
  onSubmit: (payload: SubmitPayload) => void
}

export function RequestForm({ disabled, onSubmit }: Props) {
  const [request, setRequest] = useState('')
  const [energy, setEnergy] = useState<'Low' | 'Medium' | 'High'>('Medium')
  const [approve, setApprove] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!request.trim() || disabled) return
    onSubmit({ request: request.trim(), energy, approve })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <textarea
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        disabled={disabled}
        rows={3}
        placeholder="e.g. Research the top 3 CRM tools, write a comparison report, and draft an email to my manager"
        className="w-full resize-none rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-950 px-4 py-3 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60"
      />

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          Energy
          <select
            value={energy}
            onChange={(e) => setEnergy(e.target.value as typeof energy)}
            disabled={disabled}
            className="rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-950 px-2 py-1 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60"
          >
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
          </select>
        </label>

        <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input
            type="checkbox"
            checked={approve}
            onChange={(e) => setApprove(e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          Allow real-world actions (e.g. actually send email)
        </label>

        <button
          type="submit"
          disabled={disabled || !request.trim()}
          className="ml-auto inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
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
