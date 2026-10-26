FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 INCIDENT_DB=/data/incidents.db
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && mkdir /data
COPY app.py index.html ./
EXPOSE 8000
VOLUME ["/data"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
