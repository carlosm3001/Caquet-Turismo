FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3030

# El script main.py está diseñado para cargar CLASE1.rdf en RAM al inicio
CMD ["python", "main.py"]
