FROM python:3.12-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
COPY ./gunicorn_config.py /code/gunicorn_config.py
COPY ./initdb.py /code/initdb.py

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./engine /code/engine
COPY ./webapp /code/webapp

EXPOSE 80

CMD ["gunicorn","--config", "gunicorn_config.py", "webapp:app"]
