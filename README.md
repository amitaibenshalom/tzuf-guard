# TzufGuard

TzufGuard is a web platform and Flask API for managing Wi-Fi door sensors. It is
deployed to Vercel and stores production data in Turso/libSQL.

It serves:

- `/` as the public product homepage and live sensor demo.
- `/login` and `/register` as dedicated authentication pages.
- `/reset-password` as the password-recovery destination.
- `/app/doors` as the authenticated door-management application.
- `/api/...` as the browser, mobile client, and sensor REST API.
- Turso/libSQL as the only production database.

Users can register with name, email, and password or sign in with Google. The
authenticated application supports multiple doors, one-time sensor setup
phrases, live status, editing, deletion, and paginated state-change history.

## Structure

```text
tzuf-guard/
├── api/index.py          # Vercel Python entrypoint
├── app/                  # Flask package, API, services, and static web assets
├── migrations/           # Alembic migrations
├── public/               # CSS and JavaScript served by Vercel's CDN
├── templates/            # web application shell
├── tests/                # focused API tests
├── requirements.txt      # production dependencies
├── requirements-dev.txt  # test/dev dependencies
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
CORS_ORIGINS=https://your-domain.example
NOTIFICATIONS_ENABLED=true
ABLY_API_KEY=<server-only Ably API key with publish and subscribe capability>
ABLY_TOKEN_TTL_SECONDS=3600
JWT_ACCESS_TOKEN_EXPIRES_SECONDS=2592000
GOOGLE_OAUTH_CLIENT_IDS=your-android-client-id.apps.googleusercontent.com,your-web-client-id.apps.googleusercontent.com
GOOGLE_WEB_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
PUBLIC_DEMO_DOOR_ID=<door database id shown by the doors API>
PUBLIC_DEMO_DOOR_LABEL=Amitai's door
PASSWORD_RESET_BASE_URL=https://your-domain.example/reset-password
PASSWORD_RESET_EXPIRES_MINUTES=60
MAIL_FROM=no-reply@your-domain.example
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<smtp login>
SMTP_PASSWORD=<smtp key>
SMTP_USE_TLS=true
```

`PUBLIC_DEMO_DOOR_ID` selects the single door shown in the large live demo on
the public homepage. The public endpoint exposes only the configured label, the
current `opened`/`closed` state, and its elapsed duration. It never exposes the
door's owner, location, device name, setup phrase, exact timestamps, or history.

Production startup fails fast if Turso or secrets are missing.

For Google login, add `https://amitaibenshalom.com` as an authorized JavaScript
origin for the web OAuth client in Google Cloud. Use the same web client ID in
both `GOOGLE_WEB_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_IDS`.

## Install Locally

```bash
cd tzuf-guard
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
http://localhost:5000/login
http://localhost:5000/app/doors
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
- `POST /api/auth/google`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `GET /api/me`

Doors:

- `POST /api/doors` — creates a door and returns its setup phrase once
- `GET /api/doors`
- `GET /api/doors/<id>`
- `GET /api/doors/<id>/events`
- `PATCH /api/doors/<id>`
- `DELETE /api/doors/<id>`
- `POST /api/doors/<id>/setup-token` — replaces and returns the setup phrase

Device:

- `POST /api/door-status`

Push:

- `POST /api/push-devices`
- `DELETE /api/push-devices`

Realtime:

- `POST /api/realtime/token` — issues a short-lived, subscribe-only Ably JWT for the signed-in user's private door channel
- `POST /api/public/demo-door/realtime-token` — accepts a stable anonymous `client_id` (`demo-` plus 32 lowercase hex characters) and issues a short-lived, subscribe-only JWT for the public demo channel

Authenticated app endpoints require:

```http
Authorization: Bearer <access_token>
```

The sensor uses only the per-door setup phrase when posting `/api/door-status`.
Every report refreshes the door's current status and last-seen time. History is
created only when the status changes, so reconnects and repeated reports do not
pollute the activity timeline.

## Security Notes

- Passwords are hashed.
- Door setup phrases contain about 77.5 bits of entropy and are SHA-256 hashed before
  storage.
- A setup phrase appears only in the create/regenerate response. It cannot be
  retrieved later because only its hash is stored.
- API responses never expose stored token hashes or password hashes.
- Users can only access their own doors.
- Ably API keys remain server-only. Browser and mobile clients receive short-lived JWTs scoped to their own private channel with subscribe-only capability.
- The homepage demo uses a separate public channel whose payload contains only the same safe status fields exposed by the public demo endpoint.
- Turso remains the source of truth. Ably publishes only committed status changes, and an Ably outage does not reject sensor reports.
- CORS is scoped to `/api/*`.
- Push notification delivery sends Expo push notifications when `NOTIFICATIONS_ENABLED=true`.
