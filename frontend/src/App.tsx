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
    <div className="relative flex h-screen overflow-hidden bg-[#05060b] text-gray-100">
      {/* Ambient glow field - purely decorative, sits behind everything */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden hud-grid">
        <div className="animate-drift absolute -left-32 -top-32 h-[32rem] w-[32rem] rounded-full bg-cyan-500/20 blur-[120px]" />
        <div className="animate-drift-slow absolute -bottom-40 right-0 h-[36rem] w-[36rem] rounded-full bg-violet-600/20 blur-[130px]" />
      </div>

      <Sidebar agents={agents} healthy={healthy} onOpenSettings={() => setSettingsOpen(true)} />

      <main className="relative z-10 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-10">
          <header className="mb-6">
            <h1 className="bg-gradient-to-r from-cyan-300 via-sky-200 to-violet-300 bg-clip-text text-2xl font-bold tracking-tight text-transparent">
              What do you want to do?
            </h1>
            <p className="mt-1.5 font-mono text-sm text-cyan-100/40">
              &gt; multi-agent orchestration :: plan → agents → tools → verify
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
                  className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/20 bg-white/[0.03] px-3 py-1.5 text-xs text-cyan-100/60 backdrop-blur-sm transition hover:border-cyan-400/50 hover:text-cyan-200 hover:shadow-[0_0_16px_rgba(34,211,238,0.15)]"
                >
                  <Sparkles className="h-3 w-3 text-violet-400" />
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
