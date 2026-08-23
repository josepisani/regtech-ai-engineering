# Cloud Run image. Cloud Run sets $PORT (default 8080); the app must listen on it.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
# Shell form so ${PORT} is expanded at runtime.
CMD ["sh", "-c", "uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT}"]
