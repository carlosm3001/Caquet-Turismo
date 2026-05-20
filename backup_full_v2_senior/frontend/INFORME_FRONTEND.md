# Informe de Interfaz: Portal Turístico Inteligente

Esta carpeta contiene el código de la interfaz de usuario, diseñada para ser intuitiva y basada en datos.

## 🎨 Diseño y UX
- **Estilo:** Moderno (Glassmorphism), con tipografía 'Outfit'.
- **Responsive:** Adaptable a móviles y escritorio.
- **Vistas Dinámicas:** El contenido cambia según el rol del usuario (Turista, Lugar, Admin).

## 👥 Roles de Usuario
1. **Turista:**
   - Explorador de lugares con fotos y detalles.
   - Acceso al chat inteligente Amazonia-IA.
2. **Propietario de Lugar:**
   - Gestión CRUD (Crear sitios) para alimentar la ontología.
3. **Super Administrador:**
   - Auditoría de usuarios registrados.
   - Dashboard de estadísticas SPARQL.
   - Portal de APIs (Estilo Dataestur) para pruebas técnicas.

## 🤖 Interacción con la IA
El widget de chat permite a los turistas hablar con el motor semántico. La IA no solo responde texto, sino que **actualiza la galería de lugares** automáticamente según lo que el usuario esté buscando.

## 📂 Archivos
- `index.html`: Aplicación de una sola página (SPA) con lógica en JavaScript nativo (Vanilla JS).
