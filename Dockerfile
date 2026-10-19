FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/pipeline
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline ./pipeline
RUN mkdir -p data docs/data reports && useradd --create-home pulse && chown -R pulse /app
USER pulse

CMD ["python", "-m", "pulse.run"]
