# Trichess
[![Docker](https://github.com/ondrolexa/trichess/actions/workflows/docker-image.yml/badge.svg)](https://github.com/ondrolexa/trichess/actions/workflows/docker-image.yml)

A web application for 3-player chess on hexagonal board. Proof of concept

##  Requirements

- **Python**: 3.14+ (see `.python-version`)
- **Framework**: Flask with Flask-SQLAlchemy, Flask-Login, Flask-JWT-Extended, Flask-RESTX, Flask-Migrate
- **Frontend**: Konva.js (canvas), Bootstrap 5, vanilla JavaScript
- **Database**: PostgreSQL 17 (psycopg 3). The test suite also runs on in-memory SQLite.

## How to install

Trichess uses [uv](https://docs.astral.sh/uv/) to manage Python and dependencies — install it first
(`curl -LsSf https://astral.sh/uv/install.sh | sh`, or see the uv docs for Windows). Then, from the trichess
project's root folder:

```bash
uv sync              # creates .venv with Python 3.14+ and installs app + dev dependencies from uv.lock
uv sync --no-dev     # runtime dependencies only
```

For development, also install the git hooks (ruff lint/format, uv.lock check, tests) once:
```bash
uv run pre-commit install
```

Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`; change them with `uv add <pkg>` /
`uv add --dev <pkg>` / `uv remove <pkg>` rather than editing the lockfile.

## Running the application

Local development runs Flask on the host and PostgreSQL in Docker
(`docker-compose.dev.yml`, published on `127.0.0.1:5432` only). Put these in `.env`:

```bash
POSTGRES_PASSWORD=devpassword
SQLALCHEMY_DATABASE_URI=postgresql+psycopg://trichess:devpassword@localhost:5432/trichess
```

To start from a copy of production, put its latest dump at `instance/trichess.sql` first. An empty
database initialises itself from that file:

```bash
mkdir -p pgdata instance                        # once; the data dir must exist and be yours
docker compose -f docker-compose.dev.yml up -d
uv run flask --app=webapp run
```

The application will be available at `http://localhost:5000`. To re-initialise from a newer dump:
`docker compose -f docker-compose.dev.yml down && rm -rf pgdata && mkdir pgdata`, then `up -d` again. With no dump available, create
an empty schema instead: `uv run python initdb.py && uv run flask --app=webapp db stamp head`.

There are three compose files:

| File | Runs |
|---|---|
| `docker-compose.dev.yml` | PostgreSQL only, for Flask on the host |
| `docker-compose.yml` (default) | The whole stack in containers, built from the working tree, without Traefik. App on `http://localhost:8080`, SSE on `http://localhost:8090`: `docker compose up -d --build`. The header comments explain the setup. |

The dev and default files share `./pgdata` and both publish `127.0.0.1:5432`, so only one of them runs at a time.

## Linting, formatting and tests

```bash
uv run ruff check --fix .    # lint (pyflakes/pycodestyle rules + import sorting)
uv run ruff format .         # format
uv run pytest                # tests (in-memory SQLite)
TEST_DATABASE_URL=postgresql+psycopg://trichess:devpassword@localhost:5432/trichess_test uv run pytest
```

The second form runs the suite against a throwaway PostgreSQL database, whose name must contain `test`.
Create it first with `docker compose -f docker-compose.dev.yml exec postgres createdb -U trichess trichess_test`.
CI runs both. The `dump-db` tests skip themselves when `pg_dump` (PostgreSQL 17 client) isn't installed.

Ruff is configured in `pyproject.toml` (`[tool.ruff]`). GitHub Actions runs the same three checks on every
pull request and push to `main`, and only builds and pushes the Docker image (which installs dependencies
with uv from `uv.lock`) once they pass.

## For developers

The application uses environment variables for configuration, loaded from a `.env` file via `python-dotenv`.

### Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_SECRET_KEY` | Secret key for Flask sessions and CSRF protection (required unless `DEBUG=true`) | — |
| `JWT_SECRET_KEY` | Secret key for JWT token signing (required unless `DEBUG=true`) | — |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:5000` |
| `DEBUG` | Enable Flask debug mode, also for `flask` CLI and cron commands (no push notifications are sent) | `false` |
| `REDIS_URL` | Redis connection URL for the bot's background move queue (RQ) | `redis://localhost:6379/0` |
| `BOT_DEPTH` | Minimax search depth for bot moves/votes (higher = stronger but slower) | `3` |
| `SINGLE_PLAYER_NOTIFICATIONS` | Send live "your turn"/"game over" push notifications for 1-human-vs-2-bots games | `false` |
| `BOT_GAMES_REMOVAL` | Delete finished bot games (and their logs) older than this many minutes via `remove-bot-games`; `0` disables deletion | `15` |
| `API_TOKEN_USERS` | Comma-separated allowlist of usernames who may mint an API bearer token via `POST /token` (including Swagger UI's "Authorize" dialog) | `` (empty — nobody allowed until set) |
| `SSE_URL` | Base URL of the live-update service (`sse/app.py`) for the board page. Empty = same origin (production behind Traefik); in local dev e.g. `http://localhost:8090` | `` (same origin) |
| `SQLALCHEMY_DATABASE_URI` | Database URL, shared by the app, worker and SSE service: `postgresql+psycopg://user:pw@host:5432/trichess` (set by the compose files). Required: the app and SSE service refuse to start without it | — |
| `POSTGRES_PASSWORD` | Password of the `trichess` role in the `postgres` compose service (Compose interpolates it into the URL above) | — |
| `SSE_HEARTBEAT_INTERVAL` | Seconds between SSE heartbeat comments | `15` |
| `GA_MEASUREMENT_ID` | Google Analytics 4 measurement ID (`G-XXXXXXXXXX`). Loaded only after the visitor accepts the consent banner; never rendered in debug mode or for admin. Tracks page views and account/lobby events only, not gameplay | `` (empty — analytics disabled) |

### Security Notes
- **Always change the default secret keys in production**.
- Restrict `CORS_ORIGINS` to trusted domains only.
- Set `DEBUG=false` in production.
- Restrict `API_TOKEN_USERS` to trusted accounts — it gates direct API access, not browser gameplay (every logged-in player still gets their own token server-side for the board UI).

## Running the application
```bash
flask --app=webapp --debug run
```

## Database Migrations

The application uses Flask-Migrate for database version control.

### Create a new migration
```bash
flask --app=webapp db migrate -m "Description of changes"
```

### Apply migrations
```bash
flask --app=webapp db upgrade
```

### Rollback migrations
```bash
flask --app=webapp db downgrade
```

## Trichess CLI

Purge old logs (default to 90 days)
```bash
flask --app=webapp purge-logs --days 365
```

Re-trigger any active game stuck waiting on a bot (safety net for a queued
job lost to e.g. a Redis restart — see `crontab`)
```bash
flask --app=webapp bot-sweep
```

Rebuild `instance/opening_book.json` from finished games in the database
(used by the bot's opening-book move selection)
```bash
flask --app=webapp build-opening-book
```

Write a plain-SQL dump of the database (default `instance/trichess.sql`;
`--file` to choose another path; runs every 6 hours via cron). The postgres service loads this file
whenever it starts with an empty data dir, which is how both a restore and local dev setup work.
```bash
flask --app=webapp dump-db [--file out.sql]
```

One-time copy of the legacy SQLite database into an empty PostgreSQL database (see
[POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md) for the production cut-over)
```bash
flask --app=webapp sqlite-to-postgres --sqlite instance/trichess.db
```

Delete finished games with a bot player, and their logs, once older than
`BOT_GAMES_REMOVAL` minutes (default `15`; `0` disables; see `crontab`)
```bash
flask --app=webapp remove-bot-games --minutes 15
```

## Project Structure

```
engine/               # Pure Python 3-player chess game logic
  GameAPI             # Main class - replay/validate moves from slog
webapp/               # Flask web application
  main.py             # Flask app entry point, DB init, logging (GAME level, DBHandler), CLI commands
  views.py            # HTML routes (login, games, profile, admin)
  api.py              # Flask-RESTX API at /api/v1/*
  models.py           # SQLAlchemy models: User, TriBoard, Score, Log
  botplayer.py         # RQ job that runs a bot's move/vote and persists it via the API
  forms.py            # WTForms for registration, login, profile, etc.
  configuration.py    # App configuration and environment variable loading
  static/             # Static assets: ondro.js, filio.js, CSS, YAML themes/pieces
  templates/          # Jinja2 HTML templates (board_ondro.html, board_filio.html, etc.)
migrations/           # Alembic database migration scripts
instance/             # opening_book.json, the legacy SQLite trichess.db and trichess.sql from dump-db,
                      # also postgres' initdb seed folder (gitignored, bind-mounted)
pgdata/               # PostgreSQL data dir in production (gitignored)
.env                  # Environment variables (gitignored)
.env.example         # Template for environment variables
crontab              # Cron job configuration (resend-notifications, bot-sweep, remove-bot-games, dump-db)
```

## Key Concepts

### slog (Serialized Game Log)
- **4 characters per move/vote**: The canonical game state format.
  - **Moves**: 4 chars encoding from→to positions + optional promotion.
  - **Votes**: `r`/`s` (individual) or `R`/`S` (set-vote) with `A`=accept, `D`=decline.

### view_pid
- Perspective for gid↔hex mapping:
  - `0` = Bottom player
  - `1` = Left player
  - `2` = Right player

### TriBoard.status
- `0` = Available/waiting for players
- `1` = Active game in progress
- `2` = Finished/archived game

### Endgame detection & Score.tag
- `GameAPI.endgame()` is the single classifier all game-ending logic (API response, DB persistence, scoring) goes
  through — returns `"checkmate"`, `"draw"`, `"resignation"`, `"stalemate"`, `"repetition"`, or `None` while the
  game is still ongoing.
- Draw and resignation require all/enough players to vote; checkmate and stalemate both come down to "the on-move
  player has no legal move anywhere", split by whether their king is currently attacked; threefold repetition is
  detected automatically via a position-signature counter built while replaying the slog (`GameAPI._position_signature()`/`position_counts`) — no player action needed for stalemate or repetition.
- `Score.tag`: `N`=checkmate, `D`=draw, `R`=resignation, `S`=stalemate, `T`=threefold repetition.
- Scoring: checkmate splits 2.0 points proportionally by attacking pieces; resignation gives the non-accepting
  player 2.0; draw/stalemate/repetition all split 2/3 point to each of the three players.

### Log Model
- Logs are stored in the `log` table for analytics and debugging.
- Three levels: `ERROR`, `WARNING`, and custom `GAME` (value 25).
- `GAME`-level logs track game creation, moves, and completion with `user_id`/`board_id` foreign keys.
- All `logger.error()` and `logger.warning()` calls across the app are captured automatically via `DBHandler`.
- Cleanup: `flask --app=webapp purge-logs [--days 90]` deletes old entries.

### Admin Check
- Hardcoded check: `g.user.id == 1` (see `views.py`).
- Default admin user is auto-created with `id=1`, `username='admin'` (see `models.py` DDL).
- Admin's profile page includes a user selector to view any player's rating chart.

### Maintenance mode
- The admin turns it on/off from the **Maintenance mode** card on their profile page (stored in the `setting` table, so every process sees it).
- While on, every request except the admin's gets the "Maintenance in progress" page (HTTP 503 with `Retry-After`). API calls get a JSON 503, and open board pages reload into the maintenance page. Only `/login`, `/logout` and static files stay reachable, and only the admin can sign in.
- Bots, `resend-notifications` and `bot-sweep` pause. Once it's turned off, the 5-minute `bot-sweep` resumes any bot games that are waiting.

### User Approval
- New users have `active=False` initially and require email verification (or admin approval) to log in.

### CLI Commands
- **`resend-notifications`**: Send turn reminders for games inactive >24h (runs via cron — see `crontab`).
- **`purge-logs`**: Delete log entries older than `--days` (default 90).
- **`bot-sweep`**: Re-trigger any active game whose on-move seat is a bot (runs via cron — see `crontab`).
- **`build-opening-book`**: Rebuild `instance/opening_book.json` from finished games in the database; weekly via cron (Sunday 03:00).
- **`dump-db`**: Write a SQL dump of the database to `instance/trichess.sql` (or `--file`); every 6 hours via cron.
- **`sqlite-to-postgres`**: One-time, verified, all-or-nothing copy of the legacy SQLite database into an empty PostgreSQL database (`--sqlite PATH`).
- **`remove-bot-games`**: Delete finished games with a bot player, and their logs, older than `--minutes` (`BOT_GAMES_REMOVAL` env var, default `15`; `0` disables; runs every 5 minutes via cron — see `crontab`).

### Bot players
- A game's owner can fill an empty seat with one of 2 dedicated bot accounts (`Bot 1`/`Bot 2`, `User.is_bot=True`) from the `/join` lobby.
- Whenever it becomes a bot's turn (a move or a vote response), `webapp/botplayer.py` enqueues an RQ job (`bot` queue) that computes the move via `engine.bot.choose_move`/`choose_vote` and persists it through the same `POST /api/v1/manager/board` endpoint a browser uses.
- Games with a bot seat are casual: no `Score` rows and no rating impact for any participant.
- A game seated with exactly 1 human and 2 bots (solo practice) has its live "your turn"/"game over" push notifications suppressed by default — set `SINGLE_PLAYER_NOTIFICATIONS=true` to re-enable them. `resend-notifications`' 24h-stale-game reminder always ignores this setting, so a player who genuinely forgot they had a game running still gets pinged.

### Background jobs (RQ)
- Requires Redis (`REDIS_URL`) and a running worker: `rq worker notifications bot --url $REDIS_URL` (see the `trichess-worker` service in `docker-compose.yml`) — 2 queues, listed in priority order so a slow bot search never delays a time-sensitive notification/email behind it in the same worker.
- `webapp/notifications.py`: push notifications (`webapp/main.py`'s `post_notification`) and outgoing email (`webapp/email.py`'s `send_email`) both queue onto the `notifications` queue instead of blocking the request on ntfy.sh/SMTP. Both wrappers keep their existing synchronous checks (debug mode / `MAIL_SERVER` configured) so nothing gets queued needlessly; actual send failures are logged in the worker, not surfaced back to the caller.

### Live board updates (SSE)
- `webapp/events.py` publishes a Redis pub/sub ping (one channel per board id) whenever `GameBoard.post()` (`webapp/api.py`) commits a move or vote — from a real human POST or `webapp/botplayer.py`'s in-process re-entry into that same endpoint, same code path either way.
- `GET /api/v1/manager/board/events?id=<id>&jwt=<token>` is served by a separate async service, `sse/app.py` (Starlette + uvicorn, `uvicorn sse.app:app --port 8090`; It streams these as Server-Sent Events to any seated player's open board page. `webapp/static/ondro.js` opens one on page load and refetches full state (`boardReset()`) on each ping — it never trusts the pushed payload. Auth on this one route is query-string-only (`?jwt=`, no `Bearer` prefix), since browsers' `EventSource` API can't set custom headers; every other endpoint stays header-only.
- Each open tab costs one coroutine (tens of KB) rather than a gunicorn thread, and the whole service shares a single Redis pattern subscription — 1000 concurrent streams measured at about 35 MB extra RSS.
- Local dev: run `uvicorn sse.app:app --port 8090` next to `flask run`, and set `SSE_URL=http://localhost:8090` and the Flask origin in `CORS_ORIGINS` in `.env`.

### External Services
- Uses `ntfy.mykuna.eu` for push notifications (non-debug mode only).

### Various
Analyze gamelogs in Python
```python
from webapp.main import app
from webapp.models import Log

with app.app_context():
    for row in Log.query.filter_by(level="GAME").order_by(Log.created_at).all():
        print(row.created_at, row.message, row.user.username, row.board_id)
```
