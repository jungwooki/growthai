FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 growth
COPY server.py index.html ./
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY data/ ./data/
USER growth
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips ${TRUSTED_PROXY_IPS:-127.0.0.1}"]
