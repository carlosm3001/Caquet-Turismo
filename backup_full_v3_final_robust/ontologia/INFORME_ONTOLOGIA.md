# Informe del Núcleo Semántico: Ontología RDF/OWL

Esta carpeta constituye el "cerebro" del proyecto, donde reside el conocimiento estructurado.

## 📄 El Archivo Maestro (`CLASE1.rdf`)
Es una ontología desarrollada en Protégé que define:
- **Clases:** Actividad, Destino, Persona, Municipio, etc.
- **Propiedades de Objeto:** `ubicadaEn`, `perteneceA`, `gestiona`.
- **Propiedades de Datos:** `clima`, `nivelDificultad`, `email`.

## 🔄 Flujo de Datos
1. Los datos originales (CSV/Excel) fueron mapeados a la ontología.
2. El sistema permite añadir nuevos individuos en tiempo real desde la aplicación (Gestión CRUD).
3. Las consultas SPARQL permiten extraer relaciones que no son evidentes en una base de datos SQL tradicional.

## 📊 Estadísticas del Modelo
El Administrador puede ver el número total de **tripletas** (Sujeto -> Predicado -> Objeto) a través del Portal de APIs, lo que garantiza la integridad del modelo.
