# Informe Técnico: Motor Semántico (Backend)

Esta carpeta contiene la lógica de negocio y el servidor de datos de la plataforma.

## ⚙️ Tecnologías
- **Framework:** FastAPI (Asíncrono).
- **Librería Semántica:** `rdflib` para el procesamiento de RDF y ejecución de SPARQL.
- **Servidor:** Uvicorn (Puerto 8001).

## 📡 Endpoints Principales
- `POST /api/v1/login`: Gestión de sesiones por roles.
- `GET /api/v1/actividades`: Consulta de sitios turísticos con filtros dinámicos.
- `POST /api/v1/chat`: Motor de IA que traduce lenguaje natural a consultas ontológicas.
- `GET /api/v1/admin/dashboard`: Genera estadísticas semánticas en tiempo real.
- `GET /api/v1/admin/ontology/full`: Volcado total de la base de datos (tripletas).

## 🧠 Inteligencia Artificial
El endpoint de chat implementa una **Memoria de Contexto**. El servidor recuerda el municipio del que está hablando el usuario para permitir conversaciones fluidas (ej: "Busca cascadas en Florencia" -> "¿Qué hay en Morelia?").

## 📂 Archivos
- `main.py`: Código fuente del servidor y definición de la API.
