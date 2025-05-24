FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    git \
    libdbus-1-dev \
    libdbus-glib-1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install autokey keyrings.alt

COPY . .

RUN mkdir -p /app/logs

RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f python || exit 1

CMD ["python", "main.py"]