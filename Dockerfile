# syntax=docker/dockerfile:1

##############################################################################
# builder — installs Python deps into an isolated venv and fetches/verifies
# supercronic. Nothing from this stage's package manager or build toolchain
# reaches the runtime image; only the resulting venv and binary are copied
# across.
##############################################################################
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential: fallback for any dependency (e.g. PyYAML's C extension)
# that doesn't yet ship a prebuilt wheel for a Python release this new —
# free here since the whole stage is discarded. curl: fetch supercronic.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.46/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=5bcefed628e32adc08e32634db2d10e9230dbca0 \
    SUPERCRONIC=supercronic-linux-amd64

RUN curl -fsSLO "$SUPERCRONIC_URL" && \
    echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - && \
    chmod +x "$SUPERCRONIC" && \
    mv "$SUPERCRONIC" /usr/local/bin/supercronic

# Isolated venv (rather than installing into system site-packages) so the
# entire dependency set is one self-contained tree, copyable in one COPY.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /code

# Dependency manifest copied alone first so this (slow) layer only
# reinvalidates when requirements.txt itself changes, not on every source
# edit — application code is copied later, in the runtime stage.
COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

##############################################################################
# runtime — minimal final image: no compiler, no apt cache, no root.
##############################################################################
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # gunicorn_config.py defaults PORT to 80, a privileged port a non-root
    # user cannot bind(). 8080 is what the app actually listens on now —
    # docker-compose.yml's Traefik loadbalancer.server.port label is set
    # to match.
    PORT=8080

WORKDIR /code

# Fixed UID/GID 1000: matches docker-compose.yml's existing "1000:1000"
# override and typical host-bind-mount ownership for ./instance, so the
# image is correct standalone too. useradd/groupadd ship in the base Debian
# image already — no apt-get needed for this.
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --home-dir /code --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/supercronic /usr/local/bin/supercronic

COPY --chown=app:app ./crontab ./gunicorn_config.py ./start.sh /code/
COPY --chown=app:app ./engine /code/engine
COPY --chown=app:app ./webapp /code/webapp

RUN chmod +x /code/start.sh

USER app

EXPOSE 8080

CMD ["./start.sh"]
