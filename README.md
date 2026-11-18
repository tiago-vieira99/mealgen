# MealGen

A small web app that plans your weekly dinners from your own meal library.

- User accounts (sign-up / sign-in); each user only sees their own meals and plans
- Meals with a name, type (meat / fish / vegetarian), ingredients and notes
- Plans for **this week** or **next week**, saved to the database
- **Random generator** with rules:
  - which days of the week
  - dishes per dinner (1–4)
  - **exact** number of days with meat, fish and/or vegetarian ("Any" = no rule, 0 = leave it out)
  - no repeats until every meal of that type has been used
- Empty (manual) plans, per-dish editing, 🔀 to swap a single dish, "re-roll all"
- Shopping list built from the ingredients of the plan
- **Sharing**: public read-only link `/p/<uuid>` (with link previews in WhatsApp/Telegram/…),
  a PNG image (`/p/<uuid>/plan.png`), native share sheet on phones, and "reset link" to revoke the old one

Stack: FastAPI + Jinja2 (server-rendered, no frontend build), SQLAlchemy, PostgreSQL 17, Pillow.
Fonts (Fraunces, Inter — OFL) are self-hosted in `app/static/fonts`, no third-party requests.

## Run locally

```bash
cp .env.example .env
# fill in POSTGRES_PASSWORD and SECRET_KEY; for local testing set COOKIE_SECURE=false
docker compose up -d --build
open http://localhost:8000
```

Tables are created automatically on startup.

## Deploy to a VM

1. Copy the project to the VM (git, `scp`, `rsync`…) and create `.env` from `.env.example`:
   - `SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `POSTGRES_PASSWORD` — a strong password
   - `BASE_URL=https://your-domain` and `COOKIE_SECURE=true`
2. Point the domain's DNS record (A/AAAA) at the VM's IP and open ports 80 and 443.
3. Pick one:

   **A) Bundled Caddy (automatic HTTPS via Let's Encrypt)** — set `DOMAIN` in `.env`, then:
   ```bash
   docker compose --profile proxy up -d --build
   ```

   **B) A reverse proxy you already run (nginx, Traefik, …)** — `docker compose up -d --build` and point the
   proxy at `127.0.0.1:8000` (by default the app only listens on localhost). Forward
   `X-Forwarded-For` / `X-Forwarded-Proto` / `Host`. nginx example:
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
4. Once you've created the accounts you need, set `ALLOW_REGISTRATION=false` and run `docker compose up -d`
   so strangers can't sign up.

### Backups

Data lives in the `pgdata` volume. Backup / restore:

```bash
docker compose exec -T db pg_dump -U mealgen mealgen | gzip > backup-$(date +%F).sql.gz
gunzip -c backup.sql.gz | docker compose exec -T db psql -U mealgen mealgen
```

### Updating

```bash
git pull && docker compose up -d --build
```

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Database credentials | `mealgen` / `mealgen` / — |
| `SECRET_KEY` | Signs session cookies (required) | — |
| `BASE_URL` | Public URL used in share links | derived from the request |
| `COOKIE_SECURE` | Only send the session cookie over HTTPS | `false` |
| `ALLOW_REGISTRATION` | Allow new sign-ups | `true` |
| `APP_TIMEZONE` | Timezone used for "this week" | `Europe/Lisbon` |
| `APP_BIND` / `APP_PORT` | Host interface/port for the app | `127.0.0.1` / `8000` |
| `DOMAIN` | Domain for Caddy (`proxy` profile) | — |

## Tests

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12-slim \
  sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

Tests run on SQLite and cover the generator (exact rules, repeats, impossible requests) and the main flows
(sign-in, CSRF, generating, editing, sharing, isolation between users).

## Layout

```
app/
  main.py         FastAPI app, middleware, error handlers
  generator.py    random plan algorithm (pure, testable)
  image.py        PNG rendering of a plan for sharing
  models.py       User, Meal, MealPlan, PlanEntry
  icons.py        inline SVG icons
  routes/         auth, meals, plans, share (public)
  templates/      Jinja2 pages
  static/         CSS and fonts
```

Design notes:
- Each plan entry keeps a copy of the meal's name/type, so deleting a meal doesn't break old plans
  (it shows as "(deleted)").
- The schema is created with `create_all`; if the models change later, add Alembic for migrations.
