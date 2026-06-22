# Walking skeleton: end-to-end health check

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Stand up the thinnest possible end-to-end slice of the whole system so every later slice has rails to build on. A browser loads the React (Vite) app, which calls a FastAPI backend health endpoint, which confirms it can reach PostgreSQL. Everything runs together via Docker Compose. Alembic is initialized with an empty baseline migration, and a single automated test exercises the health path through the API.

This is the tracer bullet: narrow (just a health check) but complete through web → API → database, packaged for portable deploy.

## Acceptance criteria

- [ ] `docker compose up` starts three services (postgres, api, web) and they become healthy.
- [ ] FastAPI exposes a health endpoint that verifies a live database connection and returns status.
- [ ] The React app renders a shell page that calls the health endpoint and displays the result.
- [ ] Alembic is configured; `alembic upgrade head` runs cleanly against the database.
- [ ] At least one automated test hits the health endpoint and asserts a healthy response.
- [ ] All times/config assume the Asia/Karachi business timezone and UTC storage convention is documented.

## Blocked by

- None - can start immediately
