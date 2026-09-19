# Общ image за api/ (dashboard) и ingestion/ (scheduler) услугите в
# docker-compose.yml — разграничени по CMD, не по различни images.
# Само requirements-runtime.txt (не пълния requirements.txt) — тук не
# ни трябват transformers/torch/vectorbt.
FROM python:3.11-slim

WORKDIR /app

COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
