"""Post-deploy smoke test: confirm a live AgentOS API deployment actually
works, right after deploying (e.g. to Render) - not just that the
container started.

    python scripts/smoke_test.py https://agentos-api-xxxx.onrender.com
    python scripts/smoke_test.py https://agentos-api-xxxx.onrender.com --key ak_...

Checks: /health responds, /agents lists all registered agents, and a
minimal /run completes with a 'done' event. Exits non-zero on any
failure, so it can be wired into a deploy pipeline if wanted.
"""

import json
import sys
import urllib.error
import urllib.request


def _request(method, url, body=None, key=None):
    headers = {"content-type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    return condition


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    key = None
    if "--key" in sys.argv:
        key = sys.argv[sys.argv.index("--key") + 1]

    ok = True

    status, body = _request("GET", f"{base}/health")
    ok &= check("GET /health -> 200", status == 200)
    ok &= check("health payload reports ok",
               status == 200 and json.loads(body).get("status") == "ok")

    status, body = _request("GET", f"{base}/agents")
    if ok := check("GET /agents -> 200", status == 200) and ok:
        names = {a["name"] for a in json.loads(body)}
        expected = {"task", "research", "email", "code", "writer",
                   "analyst", "translator"}
        ok &= check(f"all {len(expected)} built-in agents registered",
                   expected.issubset(names))

    status, body = _request(
        "POST", f"{base}/run",
        {"request": "say hello", "energy": "Low"}, key=key)
    if status == 401 and key is None:
        print("[SKIP] /run needs an API key - this deployment has auth "
              "enabled. Re-run with --key <your key> to test it.")
    else:
        ok &= check("POST /run -> 200", status == 200)
        if status == 200:
            events = [json.loads(line) for line in body.strip().splitlines()]
            kinds = [e["type"] for e in events]
            ok &= check("run produced a plan event", "plan" in kinds)
            ok &= check("run reached a done event", "done" in kinds)
            ok &= check("run emitted metrics", "metrics" in kinds)

    print("\nAll checks passed." if ok else "\nSome checks FAILED.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
