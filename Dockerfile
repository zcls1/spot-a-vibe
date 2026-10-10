# The web server only: it serves the page and forwards snapshots to the Inference
# Endpoint (set CLEF_ENDPOINT_URL and HF_TOKEN), so the image has no model or GPU deps.
FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Most hosts set PORT for you; 8000 matches running server.py locally.
ENV PORT=8000
EXPOSE 8000
CMD gunicorn --workers 2 --threads 4 --bind 0.0.0.0:$PORT server:app
