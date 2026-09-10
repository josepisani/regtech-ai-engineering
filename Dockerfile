# Cloud Run image for Project 1. One image, two services.
#
# WHY ONE IMAGE
#   The Streamlit UI and the FastAPI endpoint are two thin adapters over the
#   same core (src/aiact/classify.py). Building them from one image is what
#   makes "the API and the UI cannot disagree about a classification" a fact
#   about the deployment rather than a claim about the source.
#
#   Cloud Run gives a container one port, so the two adapters are two services
#   from the same image, selected by APP_MODE:
#       APP_MODE=ui   (default)  the public demo
#       APP_MODE=api             the JSON endpoint
#   Deploy commands for both are in README.md.
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, in their own layer: they change far less often than the
# code, so a code edit rebuilds in seconds instead of reinstalling everything.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PYTHONUNBUFFERED is not optional here. Python buffers stdout when it is a
# pipe rather than a terminal, which is exactly what it is in a container — so
# without this, the cost log lines sit in a buffer and appear in Cloud Logging
# late, out of order, or (if the instance is recycled) never. This is the
# "remember stdout buffering" note from START-HERE Day 4.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    APP_MODE=ui \
    SPEND_CAP_USD=5.0

# Shell form so ${PORT} and ${APP_MODE} are expanded at runtime by Cloud Run,
# not frozen at build time.
#
# Streamlit flags, and why each is needed on Cloud Run:
#   --server.address=0.0.0.0   listen on the interface Cloud Run routes to
#   --server.headless=true     do not try to open a browser or ask for an email
#   --browser.gatherUsageStats=false  no telemetry from a container you deployed
CMD ["sh", "-c", "if [ \"$APP_MODE\" = \"api\" ]; then \
      exec uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT}; \
    else \
      exec streamlit run webapp/ui.py \
        --server.port=${PORT} \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --browser.gatherUsageStats=false; \
    fi"]
