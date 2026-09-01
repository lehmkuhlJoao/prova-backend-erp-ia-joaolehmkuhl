# Single-stage build: every dependency here (fastapi, sqlalchemy, psycopg2-binary,
# python-jose[cryptography], passlib[bcrypt], redis) ships a prebuilt wheel for this
# platform, so there is no compilation step to isolate in a separate builder stage —
# a multi-stage build would add complexity without shrinking the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Installed before the app code is copied so this layer stays cached across code
# changes, and only reruns when requirements.txt itself changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
