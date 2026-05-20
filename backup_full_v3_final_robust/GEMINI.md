# 🌴 Caquetá Turismo Inteligente - Memoria del Proyecto

Este archivo contiene la arquitectura y especificaciones del sistema unificado de Web Semántica y Autenticación Moderna.

## 🏗️ Arquitectura Técnica

### Backend (FastAPI - Puerto 8001)
- **Motor Semántico:** RDFLib con soporte SPARQL 1.1.
- **Base de Datos Principal:** Ontología RDF/OWL (`ontologia/CLASE1.rdf`) creada en **Protégé**.
- **Seguridad:** 
  - JWT (JSON Web Tokens) para sesiones.
  - Google OAuth2 (Authlib) para inicio de sesión social.
- **Endpoints:**
  - `/api/v1/auth/google`: Inicia el flujo de Google.
  - `/api/v1/auth/google/callback`: Recibe el perfil y genera el JWT.
  - `/api/v1/actividades`: Consulta la ontología mediante SPARQL.
  - `/api/v1/admin/dashboard`: Métricas avanzadas de la base de datos RDF.

### Frontend (SPA - Puerto 5500 / Local)
- **Tecnologías:** Tailwind CSS, ES6 JavaScript, Google Fonts (Outfit).
- **Diseño:** Estética de "Lujo Sostenible" (Verdes esmeralda, gradientes, sombras suaves).
- **Flujo de Auth:** 
  1. El usuario hace login con Google.
  2. El servidor redirige con un `?token=...`.
  3. El frontend captura el token, lo guarda en `localStorage` y limpia la URL.
  4. La sesión persiste mediante la decodificación del JWT.

## 👥 Roles del Sistema
- **INVITADO:** Puede ver la página de inicio.
- **TURISTA:** Acceso a exploración de lugares y Chat IA.
- **ADMIN / LUGAR:** Acceso a gestión CRUD (Guardar en RDF) y auditoría.

## 🔑 Variables Requeridas
El servidor requiere configurar en la consola de Google Cloud:
- **Redirect URI:** `http://127.0.0.1:8001/api/v1/auth/google/callback`

---
*Memoria generada por Gemini CLI - Mayo 2026*
