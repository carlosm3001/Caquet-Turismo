# Informe Técnico: Aplicación y API de Turismo

Este directorio contiene la lógica de negocio y la interfaz de usuario.

## Componentes Principales:

### 1. `api.py` (Servidor Flask)
- **Carga de Datos:** Importa la ontología usando `rdflib.Graph()`.
- **Rutas API:**
  - `GET /actividades`: Realiza una consulta SPARQL con filtros opcionales de municipio y categoría.
  - `GET /municipios`: Utiliza una consulta con `UNION` para encontrar todos los lugares geográficos en la ontología.
- **Optimización:** Utiliza `threaded=True` para manejar múltiples peticiones sin bloquearse.

### 2. `templates/index.html` (Single Page App)
- **Tecnologías:** HTML5, CSS3 (Vanilla), JavaScript (ES6).
- **Librerías Externas:** FontAwesome para iconos.
- **Funcionalidades Clave:**
  - **Buscador con Debounce:** Espera 300ms antes de disparar la búsqueda para optimizar recursos.
  - **AbortController:** Cancela peticiones pendientes si el usuario escribe muy rápido.
  - **LocalStorage:** Guarda el array de favoritos localmente en el dispositivo del usuario.
  - **Geolocalización Indirecta:** Genera URLs de búsqueda de Google Maps basadas en los nombres de los municipios.

## Notas de Desarrollo:
- La conexión con la ontología es relativa: `../ontologia/CLASE1.rdf`.
- Los estilos están diseñados para ser responsivos (móviles y PC).
