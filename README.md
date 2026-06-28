# TzufGuard API

Clean Flask backend for the TzufGuard smart-door product. This directory is intended to be copied into its own repository and deployed directly to Vercel.

It serves:

- `/` as a simple public homepage.
- `/api/...` as the mobile app and ESP32 REST API.
- Turso/libSQL as the only production database.

## Structure

```text
TzufGuard/
├── api/index.py          # Vercel Python entrypoint
├── app/                  # Flask app package
├── migrations/           # Alembic migrations
├── templates/            # public homepage
├── tests/                # focused API tests
├── requirements.txt      # production dependencies
├── requirements-dev.txt  # test/dev dependencies
├── vercel.json           # routes all traffic to Flask
└── .env.example
```

## Vercel Environment

Set these variables in Vercel:

```env
APP_ENV=production
SECRET_KEY=<strong random secret, at least 32 chars>
JWT_SECRET_KEY=<different strong random secret, at least 32 chars>
TURSO_DATABASE_URL=libsql://your-database-your-org.turso.io
TURSO_AUTH_TOKEN=<your Turso auth token>
CORS_ENABLED=true
CORS_ORIGINS=https://amitaibenshalom.com
NOTIFICATIONS_ENABLED=true
JWT_ACCESS_TOKEN_EXPIRES_SECONDS=2592000
```

Production startup fails fast if Turso or secrets are missing.

## Install Locally

```bash
cd TzufGuard
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
cp .env.example .env
```

Local development still uses Turso. Put your Turso URL and token in `.env`.

## Run Locally Against Turso

```bash
flask --app 'app:create_app()' run --host 0.0.0.0 --port 5000
```

Visit:

```text
http://localhost:5000/
http://localhost:5000/api/health
```

## Migrate Turso

Run migrations from this directory:

```bash
flask --app 'app:create_app()' db upgrade
```

Do this from your machine or CI before deploying API code that needs a schema change. Do not run migrations from inside a Vercel request.

## Test

Tests use an in-memory database and do not create a local SQLite file.

```bash
python3 -m pytest tests
```

## API Summary

Auth:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/me`

Doors:

- `POST /api/doors`
- `GET /api/doors`
- `GET /api/doors/<id>`
- `PATCH /api/doors/<id>`
- `DELETE /api/doors/<id>`

Device:

- `POST /api/door-status`

Push:

- `POST /api/push-devices`

Authenticated app endpoints require:

```http
Authorization: Bearer <access_token>
```

The ESP32 uses only the per-door secret token when posting `/api/door-status`.

## Security Notes

- Passwords are hashed.
- Door tokens are SHA-256 hashed before storage.
- API responses never expose door tokens or password hashes.
- Users can only access their own doors.
- CORS is scoped to `/api/*`.
- Push notification delivery is currently a service boundary with a mock logger; replace `NotificationService.send_push` with FCM when ready.
