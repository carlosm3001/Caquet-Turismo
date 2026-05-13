FROM python:3.10-slim

WORKDIR /app

# Optimización de capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

# Ejecución con Uvicorn para FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
