# IntelliGuard

IntelliGuard is a lightweight AI governance and cost-routing layer for LLM applications. It sits between a client application and multiple LLM providers (Groq, Cerebras), deciding which model to use for a given request, tracking spend against a budget, and automatically falling back to a different provider if one fails.

The goal is simple: give teams a single API to talk to LLMs through, without every team member needing to hardcode API keys, pick models manually, or worry about runaway costs.

---

## Why this exists

Most teams experimenting with LLMs end up with:
- API keys scattered across scripts and notebooks
- No visibility into how much a feature/agent is actually costing
- No fallback when a provider has an outage or rate-limits them
- No easy way to compare "what if we used a cheaper model here"

IntelliGuard addresses this by introducing a small hierarchy — **Teams → Agents → Sessions** — and routing every chat request through a central budget-aware router.

---

## Core concepts

**Team**
A top-level grouping (e.g. a department or product). Has its own budget.

**Agent**
Belongs to a Team. Represents a specific AI use-case or bot (e.g. "Support Bot", "Resume Screener"). Has its own budget.

**Session**
Belongs to an Agent. Represents one usage window/conversation context and tracks how much of its budget has been consumed.

**Chat request**
Sent against a Session. The router:
1. Checks how much of the session's budget has been used
2. Picks a model tier (`heavy` vs `light`) based on remaining budget
3. Sends the request to the preferred provider (Groq or Cerebras)
4. If that provider fails, automatically retries with the next provider in the fallback order
5. Logs token usage and cost against the session
6. Returns the response *along with* what an alternate (cheaper/optimized) route would have cost — so you can see the cost tradeoff on every call

---

## Architecture

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
             ├── cost_engine.py    → token estimation + prompt optimization for cost comparison
             └── chat.py           → calls Groq / Cerebras, handles fallback, logs usage
      │
      ▼
SQLite database (via SQLAlchemy) — stores Teams, Agents, Sessions, RequestLogs
```

### Tech stack
- **Backend:** FastAPI (Python)
- **DB:** SQLite + SQLAlchemy ORM
- **LLM Providers:** Groq (`openai/gpt-oss-120b` / `openai/gpt-oss-20b`), Cerebras (`gpt-oss-120b` / `llama3.1-8b`)
- **Vision:** Groq vision model for image-based prompts
- **Frontend:** Static HTML/JS dashboard served directly by FastAPI (`/static`)
- **Server:** Uvicorn, managed via `systemd` for auto-restart and boot persistence
- **Hosting:** AWS EC2 (Ubuntu, t2.micro — free tier)

---

## API overview

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/teams/` | POST | Create a team |
| `/api/v1/agents/` | POST | Create an agent under a team |
| `/api/v1/sessions/` | POST | Create a session under an agent |
| `/api/v1/sessions/{id}` | GET | Fetch session budget/usage |
| `/api/v1/llm/chat` | POST | Send a prompt, get routed LLM response |
| `/api/v1/llm/chat-with-file` | POST | Same as above, with a file/image attachment |
| `/health` | GET | Basic health check |
| `/docs` | GET | Auto-generated Swagger UI |

### Example: full setup flow via curl

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

---

## Local setup

```bash
# Clone
git clone https://github.com/NANDHA-luffy/intelliguard.git
cd intelliguard

# Create virtual environment
python3 -m venv app/venv
source app/venv/bin/activate

# Install dependencies
pip install -r app/requirements.txt

# Set environment variables (create a .env file inside app/)
GROQ_API_KEY=your_key_here
CEREBRAS_API_KEY=your_key_here

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` for the dashboard, `http://localhost:8000/docs` for the API explorer.

---

## Deployment (AWS EC2)

The app is deployed on an AWS EC2 `t2.micro` instance (Ubuntu, free tier eligible):

1. **Instance setup** — Ubuntu Server, `t2.micro`, security group with inbound rules for SSH (22), HTTP (80), HTTPS (443), and a custom rule opening port `8000` for the app.
2. **Code deployment** — cloned directly from GitHub onto the instance.
3. **Dependencies** — installed inside a Python virtual environment. Note: the system Python version on this Ubuntu image is newer than some packages (e.g. `tiktoken`) officially support, so `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` was set during install to allow building against it.
4. **Process management** — running as a `systemd` service (`intelliguard.service`) so it:
   - starts automatically on boot
   - restarts automatically if it crashes
   - keeps running after the SSH session closes
5. **CORS** — `CORSMiddleware` added to allow the frontend to call the API cross-origin, with `allow_credentials=False` (required when `allow_origins` is set to `"*"`, since browsers reject the `*` + credentials combination).

### systemd service file (`/etc/systemd/system/intelliguard.service`)

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

### Common ops commands

```bash
sudo systemctl status intelliguard      # check status
sudo systemctl restart intelliguard     # restart after a code change
sudo journalctl -u intelliguard -n 50 --no-pager   # view recent logs
```

### Redeploying after a code change

```bash
cd ~/intelliguard
git pull
sudo systemctl restart intelliguard
```

---

## Known issues / things to harden before production

- [ ] SQLite is fine for a demo but should move to Postgres for concurrent multi-user use
- [ ] No authentication on the API endpoints yet — anyone with the URL can create teams/agents/sessions and spend budget
- [ ] `.env` currently holds provider keys in plaintext on disk — move to AWS Secrets Manager or SSM Parameter Store for a real deployment
- [ ] No HTTPS yet — traffic is plain HTTP on port 8000; put this behind Nginx + Let's Encrypt or an ALB before going further than a demo
- [ ] CORS is currently open (`allow_origins=["*"]`) — restrict to the actual frontend origin in production

---

## License

Internal project — license TBD.
