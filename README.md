# Trichess

A web application for 3-player chess on hexagonal board. Proof of concept

##  Requirements

- **Python**: 3.14+ (see `.python-version`)
- **Framework**: Flask with Flask-SQLAlchemy, Flask-Login, Flask-JWT-Extended, Flask-RESTX, Flask-Migrate
- **Frontend**: Konva.js (canvas), Bootstrap 5, vanilla JavaScript
- **Database**: SQLite

## :hammer_and_wrench: How to install

Create a virtual environment and install app. Go ahead and open a terminal window. Then navigate to your
trichess project’s root folder. Once you’re in there, run the following commands to create a fresh environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

for Windows use Command Prompt or PowerShell:
```bash
python -m venv .venv
.venv\Scripts\activate
```

> [!NOTE]
> On Microsoft Windows, it may be required to set the execution policy in PowerShell for the user.
> You can do this by issuing the following PowerShell command:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Great! You have a fresh virtual environment within your project’s folder. Now you need to install all requirements.

Here’s the command that you need to run to install trichess:
```bash
pip install -r requirements.txt
```

For developemenmt setup, use:
```bash
pip install -r requirements-dev.txt
```

## :running: Running the application

```bash
flask --app=webapp run
```

The application will be available at `http://localhost:5000`.

## :factory: For developers

The application uses environment variables for configuration, loaded from a `.env` file via `python-dotenv`.

### Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_SECRET_KEY` | Secret key for Flask sessions and CSRF protection | `dev-fallback-change-me-in-production` |
| `JWT_SECRET_KEY` | Secret key for JWT token signing | `dev-fallback-change-me-in-production` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:5000` |
| `DEBUG` | Enable Flask debug mode | `false` |
| `REDIS_URL` | Redis connection URL for the bot's background move queue (RQ) | `redis://localhost:6379/0` |
| `BOT_DEPTH` | Minimax search depth for bot moves/votes (higher = stronger but slower) | `3` |
| `SINGLE_PLAYER_NOTIFICATIONS` | Send live "your turn"/"game over" push notifications for 1-human-vs-2-bots games | `false` |
| `BOT_GAMES_REMOVAL` | Delete finished bot games (and their logs) older than this many days via `remove-bot-games`; `0` disables deletion | `0` |

### Security Notes
- **Always change the default secret keys in production**.
- Restrict `CORS_ORIGINS` to trusted domains only.
- Set `DEBUG=false` in production.

## :rocket: Running the application
```bash
flask --app=webapp --debug run
```

## :airplane: Database Migrations

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

Delete finished games with a bot player, and their logs, once older than
`BOT_GAMES_REMOVAL` days (default `0` — disabled; see `crontab`)
```bash
flask --app=webapp remove-bot-games --days 120
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
instance/             # SQLite database (trichess.db) and opening_book.json (gitignored, bind-mounted so both persist across image rebuilds)
.env                  # Environment variables (gitignored)
.env.example         # Template for environment variables
crontab              # Cron job configuration (resend-notifications, bot-sweep)
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

### User Approval
- New users have `active=False` initially and require email verification (or admin approval) to log in.

### CLI Commands
- **`resend-notifications`**: Send turn reminders for games inactive >24h (runs via cron — see `crontab`).
- **`purge-logs`**: Delete log entries older than `--days` (default 90).
- **`bot-sweep`**: Re-trigger any active game whose on-move seat is a bot (runs via cron — see `crontab`).
- **`build-opening-book`**: Rebuild `instance/opening_book.json` from finished games in the database.
- **`remove-bot-games`**: Delete finished games with a bot player, and their logs, older than `--days` (`BOT_GAMES_REMOVAL` env var, default `0` = disabled; runs monthly via cron — see `crontab`).

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
- `GET /api/v1/manager/board/events?id=<id>&jwt=<token>` streams these as Server-Sent Events to any seated player's open board page. `webapp/static/ondro.js` opens one on page load and refetches full state (`boardReset()`) on each ping — it never trusts the pushed payload. Auth on this one route is query-string-only (`?jwt=`, no `Bearer` prefix), since browsers' `EventSource` API can't set custom headers; every other endpoint stays header-only.
- Requires `worker_class = "gthread"` in `gunicorn_config.py` — gunicorn's default `sync` worker would let a single open SSE connection permanently pin an entire worker process.
- Out of scope: `webapp/static/filio.js`/`board_filio.html` (a separate board renderer) don't get this feature.

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
