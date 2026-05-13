# Proyecto: Ventana Turística del Caquetá (Web Semántica)

Este proyecto es una plataforma interactiva para la exploración de recursos turísticos en el departamento del Caquetá, Colombia. Utiliza tecnologías de la **Web Semántica** para conectar datos de actividades, hospedajes y municipios.

## 🚀 Estado Actual del Proyecto
La aplicación es ahora una **Web App funcional** con las siguientes capacidades:

### 1. Motor Semántico (Backend)
- **Base de Datos:** Ontología en formato RDF/OWL (`CLASE1.rdf`).
- **Consultas:** Motor SPARQL integrado mediante la librería `rdflib` en Python.
- **API:** Servidor FastAPI con endpoints inteligentes:
  - `/actividades`: Búsqueda filtrada de sitios turísticos.
  - `/municipios`: Listado dinámico de todos los destinos del departamento.

### 2. Interfaz de Usuario (Frontend)
- **Navegación:** Menú lateral (Sidebar) con secciones de Inicio, Explorador, Municipios y Favoritos.
- **Interactividad:** 
  - **Buscador:** Filtrado en tiempo real por municipio.
  - **Favoritos:** Sistema de guardado local (LocalStorage) con iconos de corazón.
  - **Detalles:** Ventanas emergentes (Modales) con información completa.
  - **Conectividad:** Botones directos para **WhatsApp** (reservas) y **Google Maps** (ubicación).

## 📂 Estructura de Carpetas
- `app_turismo/`: Contiene el servidor `api.py` y la interfaz web.
- `ontologia/`: El "cerebro" del proyecto (Archivo RDF y reglas de mapeo).
- `datos_fuente/`: Archivos CSV/Excel originales con los datos crudos.
- `documentacion/`: Gráficos, infografías y presentaciones del modelo.

## 🛠️ Cómo ejecutar
1. Iniciar servidor Backend: `python backend/main.py`
2. Abrir en el navegador: `http://127.0.0.1:8001/`

### 🔑 Credenciales de Acceso
- **Email:** `admin@gmail.com`
- **Password:** `admin`
- **Google Auth:** Configurado para el puerto 8001.

---
*Desarrollado como prototipo de gestión del conocimiento basado en Ontologías.*
