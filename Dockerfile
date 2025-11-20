FROM python:3.13-slim

LABEL maintainer="alexandre.abadie@inria.fr"

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-evdev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade --no-cache-dir PyDotBot

COPY entrypoint.sh /srv/entrypoint.sh
RUN chmod +x /srv/entrypoint.sh

ENTRYPOINT ["/srv/entrypoint.sh"]
