# IntelliGuard

A lightweight AI governance and cost-routing layer for LLM apps. It sits between your app and multiple LLM providers (Groq, Cerebras), picks the right model for each request, keeps track of spend against a budget, and falls back to another provider automatically if one goes down.

## Why I built this

Every time I started experimenting with LLMs for a side project, I'd end up with API keys scattered across random scripts, zero idea how much a feature was actually costing me, and no fallback if a provider rate-limited me mid-demo. So I built IntelliGuard to fix that for myself — one API to talk to LLMs through, with budgets and fallback baked in instead of bolted on later.

## Highlights

- Tiered model routing (`heavy` vs `light`) that automatically shifts to cheaper models as a session's budget runs low
- Automatic provider failover — if Groq fails, it retries with Cerebras without the caller noticing
- Every response comes back with a live cost comparison — what you paid vs. what a cheaper route would've cost
- Deployed on AWS EC2 with systemd for auto-restart, not just running on my laptop

## How it works

Three levels of hierarchy: **Team → Agent → Session**, each with its own budget.

```
Client (browser UI)
      │
      ▼
FastAPI app (main.py)
      │
      ├── /api/v1/teams     → create/read teams
      ├── /api/v1/agents    → create/read agents (belongs to a team)
      ├── /api/v1/sessions  → create/read sessions (belongs to an agent)
      └── /api/v1/llm/chat  → the actual routing + LLM call logic
             │
             ├── model_router.py   → decides heavy vs light tier based on budget usage
             ├── cost_engine.py    → token estimation + cost comparison
             └── chat.py           → calls Groq / Cerebras, handles fallback, logs usage
      │
      ▼
SQLite (via SQLAlchemy) — Teams, Agents, Sessions, RequestLogs
```

Every chat request goes through the same loop:
1. Check how much of the session's budget is already used
2. Pick `heavy` or `light` model based on what's left
3. Call the preferred provider; if it fails, retry with the next one in line
4. Log the actual cost, and return what an alternate route would've cost

**Tech stack:** FastAPI, SQLite + SQLAlchemy, Groq & Cerebras for inference, a plain HTML/JS dashboard, Uvicorn behind systemd, hosted on an EC2 free-tier box.

## Budget controller

This is the part I care most about getting right. Each Team, Agent, and Session has its own budget, and the router checks remaining budget before every single call — not just at the end of a session. If budget is healthy it uses the better model; if it's running low it quietly drops to a cheaper one. After the call, real usage gets deducted, and I also compute what the "smart" route would've cost so the tradeoff is visible on every request instead of buried in a monthly bill.

Right now it's mostly reactive — it tracks and reports spend, and switches tiers. It doesn't yet actively shrink the size of what gets sent to the model. That's the next piece.

## What I'm working on next: cutting token usage, not just tracking it

Right now, roughly 1 word = 1 token, same as any standard tokenizer. The budget controller tells you what you spent, but it doesn't do anything to reduce it. I want to add a step before the request goes out that actually compresses the prompt — stripping repeated context, summarizing older chat history, cutting boilerplate — so a request that used to cost, say, 100 tokens ends up costing meaningfully less without losing what the model needs to answer well.

Rough plan:
- A new `token_optimizer.py` that sits right before `chat.py` builds the provider request
- Summarize long conversation history instead of resending it in full every time
- Feed the reduced count back into the session's budget so lower usage shows up as slower budget burn, not just a number in a log

Haven't built this yet — it's the next thing on my list, and I wanted to write down the plan before I lose it.

## Also on the radar: fewer wasted round-trips in the retry loop

The fallback logic works, but right now a failed call means retrying the whole thing from scratch with the next provider. I want to make that smarter — reuse whatever partial work is possible instead of just starting over — but I haven't nailed down the exact design yet, so I'm leaving this as a note to myself rather than pretending it's done.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/teams/` | POST | Create a team |
| `/api/v1/agents/` | POST | Create an agent under a team |
| `/api/v1/sessions/` | POST | Create a session under an agent |
| `/api/v1/sessions/{id}` | GET | Fetch session budget/usage |
| `/api/v1/llm/chat` | POST | Send a prompt, get routed LLM response |
| `/api/v1/llm/chat-with-file` | POST | Same, with a file/image attachment |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |

```bash
# 1. Create a team
curl -X POST http://<host>:8000/api/v1/teams/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Default Team","budget":100}'

# 2. Create an agent under that team
curl -X POST http://<host>:8000/api/v1/agents/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Default Agent","team_id":1,"budget":100}'

# 3. Create a session under that agent
curl -X POST http://<host>:8000/api/v1/sessions/ \
  -H "Content-Type: application/json" \
  -d '{"agent_id":1,"budget":100}'

# 4. Chat against that session
curl -X POST http://<host>:8000/api/v1/llm/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":1,"prompt":"Hello!"}'
```

## Running it locally

```bash
git clone https://github.com/NANDHA-luffy/intelliguard.git
cd intelliguard

python3 -m venv app/venv
source app/venv/bin/activate

pip install -r app/requirements.txt

# create app/.env with:
# GROQ_API_KEY=your_key_here
# CEREBRAS_API_KEY=your_key_here

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dashboard at `http://localhost:8000`, API docs at `http://localhost:8000/docs`.

## Deploying it (AWS EC2)

Running on a `t2.micro` Ubuntu box, free tier:

1. Ubuntu Server, security group open on 22 (SSH), 80, 443, and 8000 (the app).
2. Code pulled straight from GitHub onto the box.
3. Installed inside a venv. One gotcha: the system Python on this Ubuntu image is newer than some packages officially support (looking at you, `tiktoken`), so I had to set `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` during install to get it to build.
4. Runs as a `systemd` service so it survives reboots, crashes, and me closing my SSH session.
5. CORS is open with `allow_credentials=False` — you can't combine `allow_origins="*"` with credentials, browsers won't allow it.

**`/etc/systemd/system/intelliguard.service`:**
```ini
[Unit]
Description=IntelliGuard FastAPI Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/intelliguard
Environment="PATH=/home/ubuntu/intelliguard/app/venv/bin"
ExecStart=/home/ubuntu/intelliguard/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl status intelliguard
sudo systemctl restart intelliguard
sudo journalctl -u intelliguard -n 50 --no-pager
```

Redeploy after a change:
```bash
cd ~/intelliguard
git pull
sudo systemctl restart intelliguard
```

## Roadmap / things I know need work

- Move off SQLite to Postgres once there's real concurrent usage
- Add auth on the API — right now anyone with the URL can create teams/agents/sessions and burn budget
- Get provider keys out of a plaintext `.env` and into Secrets Manager or SSM
- Put this behind Nginx + Let's Encrypt (or an ALB) instead of raw HTTP on port 8000
- Lock down CORS to the actual frontend origin instead of `*`
- Build the token optimizer described above
- Figure out the retry-loop redesign

## License

Personal project, license TBD.
