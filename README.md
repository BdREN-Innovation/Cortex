# Django + Next.js SaaS Starter

A full-stack SaaS starter: **Django REST Framework** backend (JWT auth, subscriptions, Stripe + bKash payments, admin API) and a **Next.js 16 / React 19 / TypeScript** frontend with shadcn-style UI.

The repository holds two things:

| Path | What it is |
|------|------------|
| `backend/` + `frontend/` | The **reference application** — a working project you can run directly. |
| `template/` | The **generator** — the same app with `{{PROJECT_NAME}}` placeholders plus `setup.sh`, which scaffolds a brand-new project into a directory of your choosing. |
| `frontend-vite/` | Legacy Vite/JSX SPA, superseded by `frontend/`. Kept for reference only — do not build on it. |

If you want to **start a new product**, use the template (Path A below).
If you want to **run or hack on this repo itself**, use the manual setup (Path B below).

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Prerequisites (Windows / Linux / macOS)](#2-prerequisites-windows--linux--macos)
   - [Automated install](#automated-install)
3. [Path A — Generate a new project from the template](#3-path-a--generate-a-new-project-from-the-template)
4. [Path B — Run this repository manually](#4-path-b--run-this-repository-manually)
   - [4.1 PostgreSQL](#41-postgresql)
   - [4.2 Backend (Django)](#42-backend-django)
   - [4.3 Frontend (Next.js)](#43-frontend-nextjs)
   - [4.4 Redis (optional)](#44-redis-optional)
   - [4.5 Celery (background jobs)](#45-celery-background-jobs)
5. [Running the app](#5-running-the-app)
6. [Environment variables](#6-environment-variables)
7. [API reference](#7-api-reference)
8. [Frontend routes](#8-frontend-routes)
9. [Optional integrations](#9-optional-integrations)
10. [Testing and code quality](#10-testing-and-code-quality)
11. [Production deployment](#11-production-deployment)
12. [Troubleshooting](#12-troubleshooting)
13. [Further documentation](#13-further-documentation)

---

## 1. Architecture

```
Browser ──▶ Next.js (:3000) ──rewrite /api/*──▶ Django (:8000) ──▶ PostgreSQL
                                                     │
                                                     ├──▶ Redis      (cache, throttles, channels, Celery broker)
                                                     ├──▶ Stripe     (card payments)
                                                     └──▶ bKash      (mobile payments, BD)
```

The browser never talks to Django directly. `frontend/next.config.ts` rewrites
`/api/:path*` → `${BACKEND_URL}/api/:path*/` and `/media/:path*` → `${BACKEND_URL}/media/:path*`,
so requests stay same-origin and JWT refresh cookies work without cross-site cookie rules.
`next.config.ts` also sets the CSP and security headers, and **throws at build time if
`BACKEND_URL` is unset in production**.

Backend layout:

| App | Responsibility |
|-----|----------------|
| `accounts/` | Custom UUID `User` model, JWT auth, email verification, password reset, social login (Google/Facebook/GitHub), signup protection (captcha, honeypot, disposable-email blocklist), branding uploads, admin API (`/api/admin/`) |
| `subscriptions/` | Plans, user subscriptions, usage/limits, Stripe checkout + webhooks, bKash checkout + SNS webhooks, Celery renewal tasks |
| `reactdjango/` | Project settings, URLs, ASGI/WSGI, audit log, client-IP resolution, middleware (in a generated project this folder is renamed to your project name) |

---

## 2. Prerequisites (Windows / Linux / macOS)

| Tool | Version | Needed for |
|------|---------|-----------|
| Python | **3.12.x** | Backend. The template's `setup.sh` *enforces* 3.12.x; the pinned `psycopg2-binary==2.9.9` / `Pillow==10.2.0` wheels do not cover newer Pythons. |
| Node.js | **24.x** (LTS) | Frontend. `template/frontend/package.json` declares `engines.node: 24.x`, and `setup.sh` refuses anything else. |
| npm | **11.x** | Frontend. Also enforced by `setup.sh`. |
| PostgreSQL | 12+ (14+ recommended) | Database. The `psql` client must be on `PATH` for `setup.sh`. |
| Redis | 6+ | Optional in development; **required in production** for shared rate limits, cache, Channels and Celery. |
| Git | any recent | Cloning; on Windows it also provides Git Bash. |

Verify:

```bash
python3 --version   # 3.12.x   (Windows: py -3 --version)
node --version      # v24.x
npm --version       # 11.x
psql --version      # 12+
redis-server --version
```

### Automated install

`template/install_prerequisites.sh` detects what is missing or on the wrong version and installs it via the platform's package manager — Homebrew on macOS, apt + NodeSource on Debian/Ubuntu, dnf on Fedora/RHEL, winget on Windows. **Node.js 24.x, npm 11.x and PostgreSQL** are handled by default. **Redis is offered interactively**: when it isn't found the script asks whether you want it and, if so, how to install it. Python 3.12 is opt-in.

```bash
cd template
chmod +x install_prerequisites.sh

./install_prerequisites.sh --dry-run          # show exactly what would run, change nothing
./install_prerequisites.sh                    # Node + npm + PostgreSQL, and ask about Redis
./install_prerequisites.sh --all              # …plus Python 3.12, and don't ask whether Redis is wanted
```

#### The Redis prompt

```
ℹ Redis is optional for local development (leave USE_REDIS=False in backend/.env),
ℹ but it is required in production for shared rate limits, cache, Channels and Celery.
Do you want to install Redis now? [y/N]: y

ℹ How should Redis be installed?
  1) Native — install with dnf      and enable the service  (recommended)
  2) Docker — run redis:7 as a container on port 6379       (docker: detected)
  3) Skip   — leave USE_REDIS=False for now
```

On **Windows** option 1 becomes **WSL2** instead of a native package, since Redis has no supported native Windows build:

| Method | What it does |
|--------|--------------|
| `native` | macOS `brew install redis` + `brew services start`; Debian/Ubuntu `apt install redis-server`; Fedora `dnf install redis` — then enables the service |
| `wsl` | Runs `apt install redis-server` inside your default WSL2 distribution and starts it. Reachable from Windows at `127.0.0.1:6379` |
| `docker` | `docker run -d --name saas-redis --restart unless-stopped -p 6379:6379 redis:7`. Reuses/starts the container if it already exists |
| skip | Nothing is installed; you're reminded to keep `USE_REDIS=False` |

Detection is smarter than a binary check — an already-running Redis on `127.0.0.1:6379` (including one in WSL2 or a container) counts as installed and the prompt is skipped entirely.

| Flag | Effect |
|------|--------|
| `--with-python` | Also install Python 3.12 when missing or the wrong series |
| `--with-redis` | Install Redis without asking *whether* you want it (still asks *how*) |
| `--no-redis` | Never ask about Redis, never install it |
| `--redis-method=native\|wsl\|docker` | Choose the backend non-interactively |
| `--all` | `--with-python --with-redis` |
| `--skip-node` / `--skip-db` | Leave Node.js/npm or PostgreSQL alone |
| `-y`, `--yes` | Don't prompt before installing |
| `--dry-run` | Print every command it would run, touch nothing |
| `-h`, `--help` | Usage |

It prints a plan and asks for confirmation before changing anything, skips components that already satisfy the version requirements, and finishes with a summary plus any manual follow-ups (PATH entries, database creation, how to restart Redis). On Linux it uses `sudo` — except for the Docker route, which needs none. Run it from **Git Bash** on Windows, and reopen the terminal afterwards so PATH updates apply. With no tty (piped or `--yes`), it never blocks: Redis is skipped unless you passed `--with-redis` or `--redis-method=…`.

It installs runtimes only — it does not create the project database or the Django/npm dependencies. Run `setup.sh` (Path A) or follow Path B for that. If `setup.sh` aborts on a version check, it points you at this script.

**Windows caveats:** winget installs the *current* Node.js release; if that isn't 24.x the script tells you to use [nvm-windows](https://github.com/coreybutler/nvm-windows) (`nvm install 24 && nvm use 24`). WSL2 doesn't auto-start services, so after a reboot run `wsl -e sudo service redis-server start` (the Docker route uses `--restart unless-stopped` and comes back on its own).

Prefer to do it by hand? The per-OS commands follow.

### macOS

```bash
# Homebrew: https://brew.sh
brew install python@3.12 node@24 postgresql@14 redis git
brew services start postgresql@14
brew services start redis

# Put the versioned formulas on PATH (zsh)
echo 'export PATH="/opt/homebrew/opt/python@3.12/bin:/opt/homebrew/opt/node@24/bin:/opt/homebrew/opt/postgresql@14/bin:$PATH"' >> ~/.zshrc
exec zsh
npm install -g npm@11
```

On Intel Macs replace `/opt/homebrew` with `/usr/local`.

### Linux — Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y software-properties-common git curl build-essential \
                    postgresql postgresql-contrib libpq-dev redis-server

# Python 3.12 (deadsnakes needed on Ubuntu releases that don't ship it)
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Node.js 24 + npm 11
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g npm@11

sudo systemctl enable --now postgresql redis-server
```

### Linux — Fedora / RHEL

```bash
sudo dnf install -y git gcc python3.12 python3.12-devel \
                    postgresql-server postgresql-contrib libpq-devel redis
sudo dnf module install -y nodejs:24/common   # or: sudo dnf install nodejs
sudo npm install -g npm@11

sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql redis
```

### Windows

Install with winget (PowerShell as Administrator), or use each project's installer:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e          # pick the 24.x LTS
winget install --id PostgreSQL.PostgreSQL.16 -e   # include "Command Line Tools"
winget install --id Git.Git -e
npm install -g npm@11
```

Then, in a **new** terminal:

```powershell
py -3.12 --version
node --version
npm --version
psql --version        # if "not recognized", add C:\Program Files\PostgreSQL\16\bin to PATH
```

Redis has no official Windows build. Choose one:

- **WSL2** (recommended): `wsl --install`, then inside Ubuntu `sudo apt install redis-server && sudo service redis-server start`. It is reachable from Windows at `127.0.0.1:6379`.
- **Docker Desktop**: `docker run -d --name redis -p 6379:6379 redis:7`
- **Skip it** for local development — leave `USE_REDIS=False` and Django falls back to the local-memory cache.

> **Shell note for Windows.** `setup.sh`, `start.sh` and `setup_database.sh` are Bash scripts. Run them from **Git Bash** (installed with Git), not from PowerShell or `cmd`. Everything in Path B can also be done natively in PowerShell — both variants are given below.

---

## 3. Path A — Generate a new project from the template

Missing prerequisites? Run `./install_prerequisites.sh --all` first (see [§2](#automated-install)).

`template/setup.sh` copies the template into a new directory outside the repo, renames the Django project package, generates secrets, creates the database, installs both dependency trees, migrates, seeds Free/Pro/Enterprise plans, and writes start scripts.

**macOS**

```bash
cd template
chmod +x setup.sh
./setup.sh
```

**Linux**

```bash
cd template
chmod +x setup_linux.sh setup.sh
./setup_linux.sh
```

**Windows (Git Bash)**

```bash
cd template
./setup_windows.sh
```

`setup_windows.sh` refuses to run outside Git Bash, uses `py -3` for the interpreter, creates the venv at `backend/venv/Scripts/activate`, and additionally emits `start.cmd`, `start_backend.cmd`, `start_frontend.cmd` so you can launch the project from `cmd`/PowerShell afterwards.

You will be prompted for: project name (must be a valid Python identifier), database name/user/password/host/port, and the target directory (default: a sibling of the repo). The target **cannot** be inside `template/`. `DJANGO_SECRET_KEY` and `JWT_SIGNING_KEY` are generated for you — regenerate them for production.

At the end the script offers to delete the `template/` folder; answer `N` if you want to keep generating projects from this clone.

After it finishes, fill in the blanks in `<project>/backend/.env` and `<project>/frontend/.env` (see [§6](#6-environment-variables)) and jump to [§5 Running the app](#5-running-the-app).

---

## 4. Path B — Run this repository manually

Use this to run `backend/` + `frontend/` as they are. Clone first:

```bash
git clone <repo-url> nextdjango
cd nextdjango
```

> The reference app's Django project package is named `reactdjango` and its default database is `reactdjango_db`. `backend/requirements.txt` pins **Django 4.2**, while `template/backend/requirements.txt` targets **Django 5.2** — the template is the newer of the two.

### 4.1 PostgreSQL

Create the database and a role. Values here must match `DB_*` in `backend/.env`.

**macOS** (Homebrew Postgres creates a role named after your macOS user)

```bash
createdb reactdjango_db
psql -d reactdjango_db -c "CREATE ROLE reactdjango WITH LOGIN PASSWORD 'change-me';"
psql -d reactdjango_db -c "GRANT ALL PRIVILEGES ON DATABASE reactdjango_db TO reactdjango;"
psql -d reactdjango_db -c "GRANT ALL ON SCHEMA public TO reactdjango;"
```

`template/setup_database.sh` automates this on macOS.

**Linux**

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE reactdjango_db;
CREATE ROLE reactdjango WITH LOGIN PASSWORD 'change-me';
GRANT ALL PRIVILEGES ON DATABASE reactdjango_db TO reactdjango;
SQL
sudo -u postgres psql -d reactdjango_db -c "GRANT ALL ON SCHEMA public TO reactdjango;"
```

**Windows (PowerShell)**

```powershell
# Uses the 'postgres' superuser created by the installer; it will prompt for its password
psql -U postgres -c "CREATE DATABASE reactdjango_db;"
psql -U postgres -c "CREATE ROLE reactdjango WITH LOGIN PASSWORD 'change-me';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE reactdjango_db TO reactdjango;"
psql -U postgres -d reactdjango_db -c "GRANT ALL ON SCHEMA public TO reactdjango;"
```

> **No PostgreSQL handy?** Set `DB_ENGINE=django.db.backends.sqlite3` in `backend/.env` and Django will use `backend/db.sqlite3`. Fine for a quick look; use PostgreSQL for real work.

### 4.2 Backend (Django)

**macOS / Linux**

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# Edit .env: replace every __REQUIRED__ placeholder (see §6)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

**Windows (PowerShell)**

```powershell
cd backend
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1     # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env                     # replace every __REQUIRED__ placeholder

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

**Windows (Git Bash)** — same as macOS/Linux, except `py -3 -m venv venv` and `source venv/Scripts/activate`.

Generate the two required secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Run it twice — once for `DJANGO_SECRET_KEY`, once for `JWT_SIGNING_KEY`.

Seed the default subscription plans (optional; the automated setup does this for you):

```bash
python manage.py shell -c "
from subscriptions.models import Plan
Plan.objects.update_or_create(slug='free', defaults={'name':'Free','tier':0,'max_items':3,'price_monthly':0,'price_yearly':0,'currency':'USD','is_active':True,'features':['Up to 3 items','Basic features','Community support']})
Plan.objects.update_or_create(slug='pro', defaults={'name':'Pro','tier':1,'max_items':25,'price_monthly':29,'price_yearly':290,'currency':'USD','is_active':True,'features':['Up to 25 items','All Pro features','Priority support']})
Plan.objects.update_or_create(slug='enterprise', defaults={'name':'Enterprise','tier':2,'max_items':0,'price_monthly':99,'price_yearly':990,'currency':'USD','is_active':True,'features':['Unlimited items','All Enterprise features','Dedicated support']})
"
```

Backend is now at `http://localhost:8000` — API under `/api/`, Django admin at `/admin/`.

### 4.3 Frontend (Next.js)

**macOS / Linux / Windows (Git Bash)**

```bash
cd frontend
npm ci          # or: npm install  (if package-lock.json is out of date)
cp .env.example .env
npm run dev
```

**Windows (PowerShell)**

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Open `http://localhost:3000`. The dev defaults (`BACKEND_URL=http://localhost:8000`, `NEXT_PUBLIC_API_URL=/api`) work with the backend above without further edits.

### 4.4 Redis (optional)

Development runs without Redis: `USE_REDIS=False` makes Django use the local-memory cache, which means throttle counters are per-process. Turn it on when you want realistic rate limiting, Channels, or Celery. `template/install_prerequisites.sh` can install and start it for you on any platform (see [§2](#automated-install)); the manual commands are below.

```bash
# macOS
brew services start redis
# Debian/Ubuntu
sudo systemctl start redis-server
# Fedora/RHEL
sudo systemctl start redis
# Windows — WSL2
wsl -d Ubuntu -- sudo service redis-server start
# Windows — Docker
docker run -d --name redis -p 6379:6379 redis:7
```

Then set in `backend/.env`:

```dotenv
USE_REDIS=True
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

`USE_REDIS` defaults to **on** when `ENVIRONMENT` is production and you are not running tests.

### 4.5 Celery (background jobs)

`subscriptions/tasks.py` defines the recurring jobs (bKash renewal charges, renewal reminders, expiry sweeps) and `settings.py` carries `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` and a `CELERY_BEAT_SCHEDULE`.

**Heads up:** this repo does not yet contain a Celery application module (there is no `reactdjango/celery.py`, and nothing calls `Celery(...)`), so `celery -A reactdjango worker` will not start as-is. Until that module is added, either:

- keep `CELERY_TASK_ALWAYS_EAGER=True` so `.delay()` runs inline, or
- add a standard `celery.py` app module plus the `__init__.py` import, then run:

```bash
# worker (needs Redis running, and the venv activated)
celery -A reactdjango worker -l info
# scheduler, in a second terminal
celery -A reactdjango beat -l info
```

On Windows, run the worker under WSL2 — the prefork pool is not supported natively; `-P solo` works for light local testing.

---

## 5. Running the app

You need two processes: Django on `:8000`, Next.js on `:3000`.

**macOS / Linux**

```bash
./start.sh              # both, in one terminal
./start_backend.sh      # backend only
./start_frontend.sh     # frontend only
```

Make them executable once with `chmod +x start*.sh`.

**Windows (Git Bash)** — the root `start_backend.sh` sources `venv/bin/activate`, which does not exist on Windows. Either edit it to `venv/Scripts/activate`, or use PowerShell:

```powershell
# terminal 1
cd backend; .\venv\Scripts\Activate.ps1; python manage.py runserver 8000
# terminal 2
cd frontend; npm run dev
```

A template-generated project on Windows already includes `start.cmd`, `start_backend.cmd` and `start_frontend.cmd` for this.

| URL | What |
|-----|------|
| http://localhost:3000 | Frontend |
| http://localhost:8000/api/ | REST API |
| http://localhost:8000/admin/ | Django admin |
| http://localhost:3000/admin | In-app admin panel (staff/superuser only) |

**Smoke test:** register at `/register` → check the verification email in the backend terminal (console email backend) → log in → open `/pricing` → open `/admin` as your superuser.

---

## 6. Environment variables

### `backend/.env` (from `backend/.env.example`)

Placeholders written as `__REQUIRED__` **must** be replaced before the server will behave correctly.

| Variable | Default | Notes |
|----------|---------|-------|
| `DJANGO_SECRET_KEY` | `__REQUIRED__` | Django signing key. |
| `JWT_SIGNING_KEY` | `__REQUIRED__` | Separate key for SimpleJWT. Rotating it invalidates all tokens. |
| `DEBUG` | `True` | Set `False` in production. |
| `ENVIRONMENT` | `development` | `production` flips secure defaults (incl. `USE_REDIS`). |
| `APP_ORIGIN` / `PUBLIC_APP_URL` | `http://localhost:3000` | Frontend origin; used for CORS/CSRF and links inside emails. |
| `API_ORIGIN` | `http://localhost:8000` | Backend origin. |
| `TRUST_X_FORWARDED_PROTO` | `False` | Enable behind a TLS-terminating proxy. |
| `ALLOWED_HOSTS` | derived | Comma-separated; defaults to `localhost,127.0.0.1`. |
| `DB_ENGINE` | `django.db.backends.postgresql` | Set to `django.db.backends.sqlite3` for a file database. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | `reactdjango_db` / `__REQUIRED__` / `__REQUIRED__` / `localhost` / `5432` | |
| `USE_REDIS` | `False` (dev) | Shared cache, throttles, Channels. |
| `REDIS_HOST` / `REDIS_PORT` | `127.0.0.1` / `6379` | |
| `TRUSTED_PROXY_IPS` | — | Required behind a proxy so IP throttles see the real client IP. |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/2` | |
| `EMAIL_BACKEND` | console backend | Dev prints emails to the terminal. Switch to `django.core.mail.backends.smtp.EmailBackend` in production. |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | — | SMTP settings. |
| `DEFAULT_FROM_EMAIL` | `no-reply@example.com` | |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | — | Social login; also enable the provider in the admin panel. |
| `FACEBOOK_OAUTH_CLIENT_ID` / `_SECRET`, `FACEBOOK_GRAPH_API_VERSION` | `v25.0` | |
| `GITHUB_OAUTH_CLIENT_ID` / `_SECRET` | — | |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | — | Blank disables Stripe. |
| `BKASH_APP_KEY` / `BKASH_APP_SECRET` / `BKASH_USERNAME` / `BKASH_PASSWORD` | — | Blank disables bKash. |
| `BKASH_BASE_URL` | sandbox URL | Point at production before going live. |
| `BKASH_WEBHOOK_TOPIC_ARN`, `BKASH_WEBHOOK_URL`, `BKASH_CALLBACK_TRUSTED_IPS` | — | SNS webhook verification. |
| `SIGNUP_CAPTCHA_TTL_SECONDS`, `SIGNUP_FORM_MIN_AGE_SECONDS`, `SIGNUP_FORM_MAX_AGE_SECONDS`, `SIGNUP_DISPOSABLE_EMAIL_BLOCKLIST` / `_ALLOWLIST` | commented out | Signup protection tuning. Registration **rate limits** are configured in the admin settings UI, not here. |

### `frontend/.env` (from `frontend/.env.example`)

| Variable | Default | Notes |
|----------|---------|-------|
| `BACKEND_URL` | `http://localhost:8000` | **Server-side only.** Rewrite target for `/api/*` and `/media/*`. Required in production — the build throws without it. |
| `NEXT_PUBLIC_API_URL` | `/api` | What the browser calls. Keep it relative so requests stay same-origin. |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | — | Publishable key (`pk_test_…` / `pk_live_…`). |
| `NEXT_PUBLIC_DJANGO_ADMIN_URL` | `http://localhost:8000/admin` | Optional shortcut link in the in-app admin area. |

Anything prefixed `NEXT_PUBLIC_` is **embedded in the browser bundle** — never put a secret there.

---

## 7. API reference

All paths are relative to `http://localhost:8000`.

**Auth — `/api/auth/`**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `branding/` | Public branding (logo, colors) |
| GET | `register/captcha/` | Captcha challenge for signup |
| POST | `register/` | Create account |
| POST | `login/` | Obtain JWT + refresh cookie |
| POST | `logout/` | Blacklist refresh token |
| POST | `token/refresh/` | Rotate access token |
| GET | `social/providers/` | Enabled social providers |
| GET | `social/<provider>/start/` | Begin OAuth flow |
| GET/POST | `social/<provider>/callback/` | OAuth callback |
| POST | `send-verification-email/`, `resend-verification-email/` | Email verification |
| POST | `verify-email/` | Confirm token |
| POST | `password-reset/request/`, `password-reset/validate/`, `password-reset/confirm/` | Password reset flow |
| GET | `user/` | Current user |
| PATCH/PUT | `user/update/` | Update profile / avatar |
| POST | `user/change-password/` | Change password |
| DELETE | `user/delete/` | Delete account |

**Subscriptions & payments — `/api/`**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `plans/` | Public plan list |
| GET | `subscription/` | Current subscription |
| GET | `subscription/usage/` | Usage vs. plan limits |
| POST | `subscription/cancel/` | Cancel |
| GET | `payments/stripe/config/` | Publishable key + config |
| POST | `payments/stripe/create-checkout/` | Checkout session |
| POST | `payments/stripe/customer-portal/` | Billing portal link |
| GET | `payments/stripe/session-status/<session_id>/` | Poll checkout status |
| POST | `payments/stripe/webhook/` | **Stripe webhook endpoint** |
| POST | `payments/bkash/create/` | bKash checkout |
| GET/POST | `payments/bkash/callback/` | bKash redirect callback |
| POST | `payments/bkash/webhook/` | **bKash SNS webhook endpoint** |
| GET | `payments/bkash/status/<payment_id>/` | Poll payment |

**Admin API — `/api/admin/`** (staff only): `_gate/`, `dashboard/`, `users/`, `users/<uuid>/`, `payments/`, `payments/export/`, `settings/`, `settings/test-ai/`.

---

## 8. Frontend routes

| Route | Page |
|-------|------|
| `/` | Landing |
| `/login`, `/register` | Auth |
| `/forgot-password`, `/reset-password`, `/verify-email` | Account recovery / verification |
| `/auth/social/callback` | OAuth return handler |
| `/dashboard` | Authenticated home |
| `/profile` | Profile, avatar, password, delete account |
| `/pricing` | Plans + checkout |
| `/payment/success`, `/payment/failed` | Post-checkout |
| `/admin`, `/admin/users`, `/admin/users/[userId]`, `/admin/payments`, `/admin/settings` | In-app admin panel |

---

## 9. Optional integrations

Every integration below is inert while its keys are blank — the app runs fine without any of them.

### Stripe

1. Create products and prices in the Stripe Dashboard.
2. Put `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` in `backend/.env`; `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` in `frontend/.env`.
3. Set each plan's `stripe_price_id_monthly` / `stripe_price_id_yearly` in Django admin.
4. Point a webhook at `POST /api/payments/stripe/webhook/`. Locally:
   ```bash
   stripe listen --forward-to localhost:8000/api/payments/stripe/webhook/
   ```
   (`stripe` CLI: `brew install stripe/stripe-cli/stripe` on macOS, `winget install Stripe.StripeCli` on Windows, or the tarball on Linux.)

### bKash

1. Get merchant credentials from the bKash developer portal.
2. Fill `BKASH_APP_KEY`, `BKASH_APP_SECRET`, `BKASH_USERNAME`, `BKASH_PASSWORD`.
3. Keep `BKASH_BASE_URL` on the sandbox URL until you go live.
4. For SNS webhooks set `BKASH_WEBHOOK_TOPIC_ARN`, `BKASH_WEBHOOK_URL` and `BKASH_CALLBACK_TRUSTED_IPS`; signature verification uses the `cryptography` package.
5. Set each plan's `bkash_price_monthly` / `bkash_price_yearly` (in the smallest currency unit) in Django admin.

### Social login

Add the client ID/secret pair for Google, Facebook and/or GitHub, restart the backend, then **enable the provider in the in-app admin settings** (`/admin/settings`) — env credentials alone do not switch it on. Redirect URI: `http://localhost:8000/api/auth/social/<provider>/callback/`.

### Email

Development uses the console backend — verification and reset emails are printed in the backend terminal. For real delivery, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` plus the `EMAIL_HOST*` values.

### Branding

Logos, favicon and colors are uploaded through `/admin/settings` and served from `MEDIA_ROOT` (`backend/media/`) via `/media/`, which Next.js proxies. In production, serve `/media/` from your web server or object storage rather than Django.

---

## 10. Testing and code quality

```bash
# Backend (venv activated, from backend/)
python manage.py test                 # Django test runner
black .                               # format
flake8                                # lint

# Frontend (from frontend/)
npm run lint
npx tsc --noEmit                      # type check
npm run build                         # production build
```

`pytest` and `pytest-django` are installed, but the repo has no `pytest.ini`/`DJANGO_SETTINGS_MODULE` config yet — use `manage.py test`, or add a pytest config first.

On Windows the same commands work in PowerShell once the venv is activated.

---

## 11. Production deployment

Checklist before shipping:

- `DEBUG=False`, `ENVIRONMENT=production`, fresh `DJANGO_SECRET_KEY` and `JWT_SIGNING_KEY`.
- Real `ALLOWED_HOSTS`, `APP_ORIGIN`, `PUBLIC_APP_URL`, `API_ORIGIN` (https).
- `TRUST_X_FORWARDED_PROTO=True` and `TRUSTED_PROXY_IPS=<your proxy>` behind a load balancer — otherwise every request looks like it came from the proxy and IP throttles collapse.
- `USE_REDIS=True` with a shared Redis, so throttles and cache are consistent across workers.
- SMTP email configured; live Stripe/bKash keys and webhook secrets.
- `BACKEND_URL` set for the Next.js build (`next build` throws without it in production).
- `python manage.py collectstatic`; serve `/static/` and `/media/` from nginx/CDN, not Django.
- Run Django under `gunicorn`/`uvicorn` (ASGI entrypoint: `reactdjango.asgi:application`) behind nginx; run Next.js with `npm run build && npm start` or deploy it to a Node host.
- Run Celery worker + beat if you rely on bKash renewals (see [§4.5](#45-celery-background-jobs)).

---

## 12. Troubleshooting

**Port already in use**

```bash
# macOS / Linux
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9
```
```powershell
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

**`psql: command not found` / not recognized** — PostgreSQL client tools aren't on `PATH`. macOS: `brew link postgresql@14` or add `/opt/homebrew/opt/postgresql@14/bin`. Windows: add `C:\Program Files\PostgreSQL\<ver>\bin`.

**`pg_config executable not found` when installing `psycopg2-binary`** — you're on a Python version without prebuilt wheels, or missing headers. Use Python 3.12; on Debian/Ubuntu also `sudo apt install libpq-dev`, on Fedora `sudo dnf install libpq-devel`.

**`Activate.ps1 cannot be loaded` (Windows)** — `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then reopen the terminal.

**`setup.sh` aborts on version checks** — it enforces Python 3.12.x, Node 24.x, npm 11.x exactly, and it does not install anything itself. Run `template/install_prerequisites.sh --all` to get the right versions, or switch with `pyenv`/`nvm`. Don't edit the checks unless you accept the pinned dependencies may not resolve.

**`connection refused` from the frontend** — Django isn't running, or `BACKEND_URL` points elsewhere. Restart `npm run dev` after changing `frontend/.env`; Next.js reads env at startup.

**401 loops / logged out immediately** — `APP_ORIGIN` and the browser origin must match, and the refresh cookie only survives when calls go through the Next.js rewrite (`NEXT_PUBLIC_API_URL=/api`), not directly to `:8000`.

**Rate limits behave oddly in development** — with `USE_REDIS=False` each worker process holds its own counters. Enable Redis for consistent behaviour.

**Migrations out of sync**

```bash
python manage.py showmigrations
python manage.py migrate
```

**Rebuild dependencies from scratch**

```bash
# backend  (macOS/Linux)
rm -rf backend/venv && cd backend && python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
# frontend
rm -rf frontend/node_modules && cd frontend && npm ci
```
```powershell
# backend (Windows)
Remove-Item -Recurse -Force backend\venv; cd backend; py -3.12 -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt
# frontend
Remove-Item -Recurse -Force frontend\node_modules; cd frontend; npm ci
```

---

## 13. Further documentation

| Document | Contents |
|----------|----------|
| [`template/install_prerequisites.sh`](template/install_prerequisites.sh) | Installs missing Node.js/npm/PostgreSQL, offers Redis (native/WSL2/Docker), optional Python 3.12 |
| [`template/QUICKSTART.md`](template/QUICKSTART.md) | Condensed setup for a generated project |
| [`template/README.md`](template/README.md) | Full template documentation: features, structure, endpoints, deployment |
| [`template/STRUCTURE.md`](template/STRUCTURE.md) | Directory-by-directory map |
| [`template/SHADCN_UI_GUIDE.md`](template/SHADCN_UI_GUIDE.md) | Adding and theming shadcn/ui components |
| [`frontend/CLAUDE.md`](frontend/CLAUDE.md), [`frontend/AGENTS.md`](frontend/AGENTS.md) | Frontend conventions for AI coding agents |
| [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) | Completed Vite → Next.js migration record |
| [`ISSUES.md`](ISSUES.md) | Known issues / template hygiene audit |
