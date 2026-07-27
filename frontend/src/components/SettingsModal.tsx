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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-gray-200/80 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <label className="mt-4 block text-sm font-medium text-gray-700 dark:text-gray-300">
          API key
        </label>
        <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
          Only needed if this deployment has API keys enabled. Get one from your
          operator, or via <code className="font-mono">cli.py keys create</code> /
          Google sign-in. Stored only in this browser.
        </p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="ak_..."
          className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 px-3 py-2 text-sm font-mono text-gray-900 dark:text-gray-100 focus:border-indigo-400 focus:outline-none focus:ring-4 focus:ring-indigo-500/10"
        />

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:shadow-md"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
