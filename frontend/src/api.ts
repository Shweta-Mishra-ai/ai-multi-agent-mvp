import type { AgentEvent, AgentSpec, ExecuteResult, PendingAction } from './types'

const API_KEY_STORAGE = 'agentos_api_key'

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) ?? ''
}

export function setApiKey(key: string): void {
  if (key) localStorage.setItem(API_KEY_STORAGE, key)
  else localStorage.removeItem(API_KEY_STORAGE)
}

function authHeaders(): HeadersInit {
  const key = getApiKey()
  return key ? { Authorization: `Bearer ${key}` } : {}
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function fetchAgents(): Promise<AgentSpec[]> {
  const res = await fetch('/agents')
  if (!res.ok) throw new ApiError(`Failed to load agents (${res.status})`, res.status)
  return res.json()
}

export async function fetchHealth(): Promise<{ status: string; version: string }> {
  const res = await fetch('/health')
  if (!res.ok) throw new ApiError(`Health check failed (${res.status})`, res.status)
  return res.json()
}

export interface RunOptions {
  request: string
  energy: 'Low' | 'Medium' | 'High'
  approve: boolean
  sessionId: string | null
}

/**
 * Streams NDJSON events from POST /run, invoking onEvent as each line
 * arrives rather than waiting for the whole response - this is what
 * makes the live plan/step/result progress possible, mirroring how the
 * CLI renders the same event stream.
 */
export async function runRequest(
  opts: RunOptions,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch('/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      request: opts.request,
      energy: opts.energy,
      approve: opts.approve,
      session_id: opts.sessionId,
    }),
    signal,
  })

  if (res.status === 401) {
    throw new ApiError(
      'This deployment requires an API key. Add yours in Settings.',
      401,
    )
  }
  if (res.status === 422) {
    const body = await res.json().catch(() => null)
    throw new ApiError(
      body?.detail?.[0]?.msg ?? 'Request was rejected as invalid.',
      422,
    )
  }
  if (!res.ok || !res.body) {
    throw new ApiError(`Request failed (${res.status})`, res.status)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      onEvent(JSON.parse(line) as AgentEvent)
    }
  }
  if (buffer.trim()) {
    onEvent(JSON.parse(buffer) as AgentEvent)
  }
}

export async function executeApproved(
  actions: PendingAction[],
): Promise<ExecuteResult[]> {
  const res = await fetch('/execute', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ actions }),
  })
  if (res.status === 401) {
    throw new ApiError('This deployment requires an API key. Add yours in Settings.', 401)
  }
  if (res.status === 403) {
    throw new ApiError(
      'Your API key is restricted and cannot execute approved actions.',
      403,
    )
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(body.message ?? `Execute failed (${res.status})`, res.status)
  }
  return res.json()
}
