FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run migrations, seed, then start gunicorn
CMD ["sh", "-c", "python manage.py migrate && python manage.py setup_beat && python manage.py seed && gunicorn payout_engine.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"]
