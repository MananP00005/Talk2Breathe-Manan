# Talk2Breath — container image for Google Cloud Run
FROM python:3.12-slim

# Don't write .pyc files; stream logs straight to the console.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better build caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app.
COPY . .

# Cloud Run sends traffic to the port in $PORT (defaults to 8080).
ENV PORT=8080

# Shell form so ${PORT} is expanded at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
