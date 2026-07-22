import { useEffect, useReducer, useState } from 'react'
import { ApiError, fetchAgents, fetchHealth, runRequest } from './api'
import { Sidebar } from './components/Sidebar'
import { SettingsModal } from './components/SettingsModal'
import { RequestForm, type SubmitPayload } from './components/RequestForm'
import { RunView } from './components/RunView'
import { initialRunState, runReducer } from './runReducer'
import type { AgentSpec, ExecuteResult } from './types'

export default function App() {
  const [agents, setAgents] = useState<AgentSpec[]>([])
  const [healthy, setHealthy] = useState<boolean | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
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
    <div className="flex h-screen bg-white dark:bg-gray-950">
      <Sidebar agents={agents} healthy={healthy} onOpenSettings={() => setSettingsOpen(true)} />

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <header className="mb-6">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              What do you want to do?
            </h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Multi-agent orchestration: plan → agents → tools → verify.
            </p>
          </header>

          <RequestForm disabled={running} onSubmit={handleSubmit} />

          <div className="mt-6">
            <RunView state={state} onExecuted={handleExecuted} />
          </div>
        </div>
      </main>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}
