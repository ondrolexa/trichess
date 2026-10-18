# Trichess
[![Docker](https://github.com/ondrolexa/trichess/actions/workflows/docker-image.yml/badge.svg)](https://github.com/ondrolexa/trichess/actions/workflows/docker-image.yml)

Chess for three players on a hexagonal board, played in the browser.

- 169-cell hexagonal board with three armies and rules adapted to six directions
- Play against friends, or fill empty seats with bots
- Draws and resignations are decided by a vote of all players
- Live board updates and optional phone notifications when it's your turn
- Elo-style ratings for games between human players
- Several board themes and piece sets, including colour-blind-friendly ones

The rules and a guide to the interface are on the in-app **Help** page.

## Running it locally

You need [uv](https://docs.astral.sh/uv/) and Docker. Put a database password in `.env`:

```bash
POSTGRES_PASSWORD=devpassword
SQLALCHEMY_DATABASE_URI=postgresql+psycopg://trichess:devpassword@localhost:5432/trichess
DEBUG=true
```

Then, from the project folder:

```bash
uv sync                                          # Python 3.14+ and dependencies
mkdir -p pgdata instance
docker compose -f docker-compose.dev.yml up -d   # PostgreSQL
uv run python initdb.py && uv run flask --app=webapp db stamp head   # empty database, first run only
uv run flask --app=webapp run
```

The app is at `http://localhost:5000`. Bots, notifications and live updates also need Redis, a worker
and the live-update service. To run the whole stack in containers instead, use `docker compose up -d --build`
(app on `http://localhost:8080`).

## Tests

```bash
uv run pre-commit install    # once: lint, format and tests on every commit
uv run pytest
```

## Documentation

The full developer guide (architecture, configuration, CLI commands, deployment) is in the **For developers**
tab of the in-app Help page, visible to the admin account.

## License

See [LICENSE.md](LICENSE.md).
