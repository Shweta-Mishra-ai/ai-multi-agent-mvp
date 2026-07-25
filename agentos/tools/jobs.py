import requests

from agentos.tools import tool

# RemoteOK's API is public, unauthenticated JSON - no key/signup needed,
# unlike Upwork/Fiverr/LinkedIn which require login or an approved OAuth
# app to see real listings. It's the one source AgentOS can genuinely
# browse for real, current freelance/remote gigs.
REMOTEOK_API = "https://remoteok.com/api"


@tool(
    "Search live, real freelance/remote job listings by keyword - returns "
    "actual open gigs (title, company, tags, apply link), not a description "
    "of job platforms. Use this when asked to find freelance work to apply "
    "to.",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def find_freelance_jobs(query):
    try:
        r = requests.get(REMOTEOK_API, headers={"User-Agent": "AgentOS/0.2"},
                         timeout=20)
        r.raise_for_status()
        jobs = r.json()
    except Exception as e:
        return f"Job search unavailable ({e})."

    if not isinstance(jobs, list):
        return "Job search unavailable (unexpected response format)."

    terms = [t for t in query.lower().split() if t]
    matches = []
    for job in jobs:
        # the feed's first element is a legal notice, not a job listing
        if not isinstance(job, dict) or "position" not in job:
            continue
        haystack = " ".join([
            job.get("position", ""),
            job.get("company", ""),
            " ".join(job.get("tags") or []),
        ]).lower()
        if not terms or any(t in haystack for t in terms):
            matches.append(job)
        if len(matches) >= 10:
            break

    if not matches:
        return f"No live listings matched '{query}' right now."

    return "\n\n".join(
        f"{j.get('position')} @ {j.get('company')}\n"
        f"Tags: {', '.join(j.get('tags') or [])}\n"
        f"Apply: {j.get('url')}"
        for j in matches
    )
