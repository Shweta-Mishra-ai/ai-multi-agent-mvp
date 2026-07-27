import { useEffect, useReducer, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { ApiError, fetchAgents, fetchHealth, runRequest } from './api'
import { Sidebar } from './components/Sidebar'
import { SettingsModal } from './components/SettingsModal'
import { RequestForm, type SubmitPayload } from './components/RequestForm'
import { RunView } from './components/RunView'
import { initialRunState, runReducer } from './runReducer'
import type { AgentSpec, ExecuteResult } from './types'

const EXAMPLE_PROMPTS = [
  'Research the top 3 CRM tools and write a comparison report',
  'Find freelance web developer jobs and summarize the best fits',
  'Draft a follow-up email to a client about a delayed shipment',
  'Analyze this month’s expenses and suggest where to cut costs',
]

export default function App() {
  const [agents, setAgents] = useState<AgentSpec[]>([])
  const [healthy, setHealthy] = useState<boolean | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [requestText, setRequestText] = useState('')
  const [state, dispatch] = useReducer(runReducer, initialRunState)

  useEffect(() => {
    fetchHealth()
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false))
    fetchAgents()
      .then(setAgents)
      .catch(() => setAgents([]))
  }, [])

  async function handleSubmit(payload: SubmitPayload) {
    dispatch({ kind: 'start' })
    try {
      await runRequest(
        {
          request: payload.request,
          energy: payload.energy,
          approve: payload.approve,
          sessionId: state.sessionId,
        },
        (event) => dispatch({ kind: 'event', event }),
      )
    } catch (e) {
      dispatch({
        kind: 'submit-error',
        message:
          e instanceof ApiError ? e.message : 'Something went wrong. Please try again.',
      })
    }
  }

  function handleExecuted(results: ExecuteResult[]) {
    dispatch({ kind: 'executed', results })
  }

  const running = state.phase === 'running'

  return (
    <div className="flex h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-gray-950 dark:to-gray-900">
      <Sidebar agents={agents} healthy={healthy} onOpenSettings={() => setSettingsOpen(true)} />

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-10">
          <header className="mb-6">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
              What do you want to do?
            </h1>
            <p className="mt-1.5 text-sm text-gray-500 dark:text-gray-400">
              Multi-agent orchestration: plan → agents → tools → verify.
            </p>
          </header>

          <RequestForm
            value={requestText}
            onChange={setRequestText}
            disabled={running}
            onSubmit={handleSubmit}
          />

          {state.phase === 'idle' && (
            <div className="mt-4 flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setRequestText(example)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 dark:border-gray-800 bg-white/60 dark:bg-gray-900/60 px-3 py-1.5 text-xs text-gray-600 dark:text-gray-400 shadow-sm transition hover:border-indigo-300 hover:text-indigo-700 dark:hover:border-indigo-800 dark:hover:text-indigo-300"
                >
                  <Sparkles className="h-3 w-3 text-indigo-400" />
                  {example}
                </button>
              ))}
            </div>
          )}

          <div className="mt-6">
            <RunView state={state} onExecuted={handleExecuted} />
          </div>
        </div>
      </main>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}
