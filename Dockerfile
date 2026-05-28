FROM python:3.14-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.46/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=5bcefed628e32adc08e32634db2d10e9230dbca0 \
    SUPERCRONIC=supercronic-linux-amd64

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSLO "$SUPERCRONIC_URL" && \
    echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - && \
    chmod +x "$SUPERCRONIC" && \
    mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" && \
    ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

COPY ./crontab /code/crontab
COPY ./requirements.txt /code/requirements.txt
COPY ./gunicorn_config.py /code/gunicorn_config.py

RUN pip install --no-cache-dir --no-compile --upgrade -r /code/requirements.txt

COPY ./engine /code/engine
COPY ./webapp /code/webapp
COPY ./start.sh /code/start.sh

EXPOSE 80

CMD ["./start.sh"]
