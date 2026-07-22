# AgentOS web UI

React + TypeScript + Tailwind CSS (Vite). Talks to the AgentOS FastAPI
backend (`../api.py`) — see the main [repo README](../README.md) for the
full picture.

## Development

```bash
npm install
npm run dev          # http://localhost:5173, proxies API calls to :8000
```

Run `python cli.py serve` (or `uvicorn api:app`) in another terminal first
so there's an API on :8000 to talk to.

## Production build

```bash
npm run build         # -> dist/, served by api.py at "/"
```

`python cli.py serve` automatically serves this build if it exists - no
separate frontend server or CORS configuration needed in production.

## Structure

```
src/
  api.ts            # fetch helpers + NDJSON streaming parser for /run
  runReducer.ts      # turns the event stream into UI state
  types.ts           # types matching the API's event/response shapes
  components/
    Sidebar.tsx       # agent list, health indicator, settings button
    RequestForm.tsx   # request textarea, energy select, approve checkbox
    RunView.tsx        # renders the live plan/steps/verify/result/metrics
    StepCard.tsx        # one plan step with status + expandable output
    ApprovalPanel.tsx    # pending irreversible actions + approve button
    SettingsModal.tsx     # API key entry (stored in localStorage)
```
