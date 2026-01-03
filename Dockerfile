FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# The service account credentials should be mounted to this location at runtime
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service_account.json
# Token for Telegram Bot
ENV TELEGRAM_TOKEN=""
# API Key for Google Gemini
ENV GEMINI_API_KEY=""

CMD ["python", "-m", "src.bot"]
