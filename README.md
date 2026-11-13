# FlagDesk: flag submission platform

Players register, pick a lab, submit its flag, and watch a live scoreboard. Organisers get an admin panel. Built for 100 people submitting at the same time (tested with 100 simultaneous users).

## Run

Local, no Docker:

    pip install -r requirements.txt
    ADMIN_PASSWORD=choose-one uvicorn app.main:app --port 8000 --workers 2

Docker with Postgres:

    cp .env.example .env
    docker compose up --build

Open http://localhost:8000 and sign in as the organiser (`ADMIN_USERNAME` / `ADMIN_PASSWORD`). If `ADMIN_PASSWORD` is empty, a random one is printed in the logs on first start.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| EVENT_NAME | VULNMARKET CTF | Title shown in the UI |
| ADMIN_USERNAME / ADMIN_PASSWORD | organiser / random | Organiser login |
| EVENT_CODE | empty | If set, players must enter it to register |
| REGISTRATION_OPEN | 1 | Set 0 to close sign-ups |
| MAX_PARTICIPANTS | 0 | Cap on players, 0 means no cap |
| WRONG_LIMIT / WRONG_WINDOW | 8 / 60 | Wrong submissions allowed per player per window (seconds) |
| DATABASE_URL | SQLite in data/ | Use Postgres for the real event |
| SECRET_KEY | generated and saved in data/.secret | Session signing key. Set a fixed value in production |
| COOKIE_SECURE | 0 | Set 1 behind HTTPS |
| WEB_CONCURRENCY | 2 | Worker processes |

## Flags and points

The 12 VULNMARKET labs load from `challenges.seed.json` on first start. Flags are stored only as SHA-256 hashes. Edit points, visibility and flags later in the Admin tab. After the first start you can delete the flag values from the seed file. Flags are compared after trimming whitespace and Unicode normalisation, so `€`, `$` and `@` must match exactly.

## Admin tab

Live counts, edit points and visibility, replace a flag, disable a player, set a player's password, clear a player's solves, reset all scores, export the scoreboard as CSV.

## Load test

    python loadtest.py 100

Registers 100 users at the same moment. Each then fetches challenges, submits right and wrong flags and reads the scoreboard.

## Deploy on Render

`render.yaml` creates the web service and a Postgres database. Set `ADMIN_PASSWORD` and `EVENT_CODE` in the dashboard when asked. Free Postgres on Render expires after a limited time, so check this before the event.

## Notes

- Scoring is by points, with ties broken by who reached the score first.
- Each lab can be solved once per player. Concurrent duplicate submissions score only once.
- Wrong-attempt limit also blocks correct submissions until the window passes.
