import { useState } from 'react'
import { X } from 'lucide-react'
import { getApiKey, setApiKey } from '../api'

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [value, setValue] = useState(getApiKey())

  function handleSave() {
    setApiKey(value.trim())
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-cyan-500/15 bg-[#0a0c14]/95 p-6 shadow-[0_0_40px_rgba(34,211,238,0.08)] backdrop-blur-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-100">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-cyan-200"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <label className="mt-4 block text-sm font-medium text-gray-300">
          API key
        </label>
        <p className="mb-2 text-xs text-gray-500">
          Only needed if this deployment has API keys enabled. Get one from your
          operator, or via <code className="font-mono text-cyan-300/70">cli.py keys create</code> /
          Google sign-in. Stored only in this browser.
        </p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="ak_..."
          className="w-full rounded-lg border border-cyan-500/15 bg-black/30 px-3 py-2 text-sm font-mono text-gray-100 focus:border-cyan-400/50 focus:outline-none focus:ring-4 focus:ring-cyan-400/10"
        />

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm text-gray-400 hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-gradient-to-r from-cyan-500 to-violet-600 px-4 py-2 text-sm font-medium text-white shadow-[0_0_16px_rgba(34,211,238,0.35)] transition hover:shadow-[0_0_22px_rgba(34,211,238,0.5)]"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
