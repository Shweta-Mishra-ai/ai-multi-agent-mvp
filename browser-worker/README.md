---
title: AgentOS Browser Worker
emoji: 🌐
sdk: docker
app_port: 7860
---

# AgentOS browser worker

A small standalone service that renders JavaScript-heavy pages with a
real headless browser and returns their visible text - the one thing
the main AgentOS app's `fetch_url` tool cannot do (it's a plain HTTP GET,
so it sees nothing for single-page apps / client-side-rendered content).

It deploys separately from the main app because it needs real memory to
run Chromium (~300-500MB+), more than Render's free tier (512MB total)
comfortably allows. Hugging Face Spaces' free CPU tier (2 vCPU, 16GB RAM)
has plenty of headroom and costs nothing.

**What it does NOT do:** log into authenticated/private pages. There are
no credentials here - that's a much bigger, per-site problem (2FA,
CAPTCHAs, session handling) this worker doesn't attempt to solve.

## Deploying to Hugging Face Spaces

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Pick a name (e.g. `agentos-browser-worker`), set **SDK** to **Docker**,
   visibility can be Public (the worker requires its own token regardless
   - see below - so a public Space doesn't mean public access to it).
3. Once created, clone the Space's git repo it gives you, and copy the
   contents of this `browser-worker/` folder into it (or push this
   folder's contents directly as the Space's root - the `Dockerfile` and
   this `README.md`'s YAML header at the top are both required at the
   Space's root, that's how Spaces knows to build a Docker app on port
   `7860`).
4. In the Space's **Settings → Variables and secrets**, add a **secret**
   named `WORKER_API_KEY` set to any long random string you generate
   yourself (e.g. `openssl rand -hex 32`). This is required - the service
   refuses every request without it, since the Space gets a public URL
   and anyone could otherwise spend your compute running arbitrary
   browser automation.
5. Push/commit - the Space builds and deploys automatically. Check the
   **Logs** tab; first build takes a few minutes (installing Chromium).
6. Your worker's URL will be `https://<your-username>-<space-name>.hf.space`.

## Wiring it into the main AgentOS app

On the main app's deployment (Render), set:

```
BROWSER_WORKER_URL=https://<your-username>-<space-name>.hf.space
BROWSER_WORKER_TOKEN=<the same WORKER_API_KEY you generated above>
```

The research agent's `render_page` tool picks these up automatically -
no code change or redeploy of the worker needed if you rotate the token,
just update it in both places.

## Local development

```bash
cd browser-worker
pip install -r requirements.txt
playwright install --with-deps chromium
WORKER_API_KEY=dev-secret uvicorn app:app --reload --port 7860
```

```bash
curl -X POST http://localhost:7860/render \
  -H "Authorization: Bearer dev-secret" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```
