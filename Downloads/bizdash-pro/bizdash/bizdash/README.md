# BizDash — Business Automation & AI Dashboard

Customers and orders manager with role-based login, a stats dashboard, AI triage of customer
messages, and automatic team notification through n8n.

**Stack:** React + TypeScript (Vite) · FastAPI · PostgreSQL · SQLAlchemy · JWT · Docker Compose · n8n · Anthropic API

## Features
| Requirement | Where |
|---|---|
| Login + roles (`admin`, `agent`) | `backend/app/main.py` (JWT, PBKDF2 hashing). Admin is seeded from `.env`; new sign-ups are `agent`. Only admins delete records, list users and change roles |
| Customers & orders CRUD | `/api/customers`, `/api/orders`, UI tabs |
| Dashboard | `/api/stats` + Dashboard tab (orders, customers, revenue, by status, by topic) |
| Documented API on a database | Swagger at `/api/docs`, PostgreSQL in Docker (SQLite for local tests) |
| Workflow on new order | Backend POSTs to n8n webhook (3 retries, backoff); `n8n/new-order-workflow.json` emails the team |
| AI summary + classification | `backend/app/ai.py`: Claude when `ANTHROPIC_API_KEY` is set, keyword fallback otherwise. Runs in a background task so order creation stays fast |
| Tests, Docker, CI | `backend/tests`, `docker-compose.yml`, `.github/workflows/ci.yml` |

## Run it
```bash
cp .env.example .env     # replace every value: SECRET_KEY (48+ random chars), DB_PASSWORD, ADMIN_*, N8N_PASSWORD; optionally ANTHROPIC_API_KEY
# production: also set APP_ENV=production (the API refuses to start with a weak SECRET_KEY)
docker compose up --build
```
- App: http://localhost:8080  ·  API docs: http://localhost:8080/api/docs  ·  n8n: http://127.0.0.1:5678 (basic auth, local only)

### Enable the n8n notification (once)
1. Open n8n, create the owner account, **Import from file** → `n8n/new-order-workflow.json`.
2. In the *Email the team* node, add your SMTP credentials and set the recipient.
3. Toggle the workflow to **Active** (the production webhook only works when active).
4. Create an order in the app: the team receives an email with the AI summary.

### Develop without Docker
```bash
cd backend && pip install -r requirements.txt && python -m pytest -q
ADMIN_EMAIL=a@a.io ADMIN_PASSWORD=Admin12345 uvicorn app.main:app --reload
cd frontend && npm install && npm run dev      # proxies /api to :8000
```

## Deploy a demo
Any VPS with Docker: clone, create `.env`, run `docker compose up -d --build`, then put Caddy or
nginx + Let's Encrypt in front of port 8080 for HTTPS. Do not expose n8n (5678) publicly without auth.
Before going public: set a long `SECRET_KEY`, a strong `ADMIN_PASSWORD`, and a real `DB_PASSWORD`.

## Roles and permissions
| Capability | Agent | Admin |
|---|---|---|
| View dashboard, customers, orders; AI triage; CSV export | yes | yes |
| Add and edit customers and orders, change order status | yes | yes |
| Edit own profile, photo and password | yes | yes |
| **Delete** customers and orders | no | yes |
| List, create, edit, delete users, change roles, disable accounts, set or remove any user's photo | no | yes |
| Audit log (who did what) | no | yes |

The table lives in one place (`backend/app/permissions.py`); routes only ask for a permission. An admin cannot delete, demote or disable their own account, so the system always keeps an admin.

## Architecture
`routers/` (HTTP only) → `services.py` (business rules: `UserService`, `CustomerService`, `OrderService`, `StatsService`, `AuditService`) → SQLAlchemy models. Redis holds the dashboard stats cache (60 s, invalidated on every write) and login-throttle counters; if Redis is down the app falls back to in-memory and keeps working (`/api/health` shows which backend is active).

> Upgrading an existing database: this version adds user columns and an audit table, and there are no migrations yet. In development run `docker compose down -v` first (this deletes data). Alembic is the next step for production.

## Hardening included
- Login throttling in Redis (5 failures / 5 min per IP+email, then HTTP 429); disabled accounts lose access immediately
- Avatars: real type checked from file bytes (PNG/JPEG/WebP), 2 MB cap, random file names; CSV exports neutralise formula injection
- Login throttling (5 failures / 5 min per IP+email, then HTTP 429), emails normalised to lowercase
- Search input escaped (`%` and `_` are literal), input length limits, list endpoints capped with `limit`/`offset`
- Orders loaded with a single JOIN (no N+1), backend container runs as non-root with a healthcheck
- nginx: gzip, immutable asset caching, security headers

## Design decisions to explain in an interview
- **Background AI + webhook**: an AI or n8n outage never blocks order creation (fallback + retry).
- **Admin seeded from env**, open sign-up creates least-privilege `agent` accounts.
- **Nginx proxies `/api`**, so the frontend needs no CORS config.
- **Known limits / next steps**: Alembic migrations instead of `create_all`, refresh tokens, pagination,
  rate limiting on login, a durable job queue instead of FastAPI background tasks.
