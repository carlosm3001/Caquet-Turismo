# Informe General: Ventana Turística del Caquetá Inteligente

Este proyecto ha evolucionado de una aplicación Flask simple a una **Plataforma de Gestión del Conocimiento** profesional basada en Web Semántica e Inteligencia Artificial.

## 🏗️ Arquitectura Actual (v8.0)
El sistema utiliza una arquitectura desacoplada:
- **Backend:** Desarrollado con **FastAPI** (Python). Actúa como el motor semántico que consulta el archivo RDF mediante SPARQL.
- **Frontend:** Una **SPA (Single Page Application)** moderna que consume la API y ofrece experiencias personalizadas por roles.
- **Base de Datos:** Una **Ontología RDF/OWL** que centraliza el conocimiento turístico del departamento.

## 🚀 Componentes Clave
1. **Amazonia-IA:** Un agente de conversación que utiliza procesamiento de lenguaje natural para realizar búsquedas inteligentes en la ontología.
2. **Sistema de Roles:** Autenticación para Turistas, Propietarios de Lugares y un Super Administrador.
3. **Portal de Datos:** Documentación técnica estilo "Dataestur" para el acceso a datos abiertos.

## 🛠️ Ejecución rápida
1. Ir a la carpeta `backend/`.
2. Ejecutar `python main.py`.
3. Abrir en el navegador: `http://127.0.0.1:8001`.

---
*Generado por Gemini CLI - Marzo 2026*
