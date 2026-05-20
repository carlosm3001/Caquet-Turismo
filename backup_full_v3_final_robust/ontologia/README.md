# Informe: Ontología de Turismo
Esta carpeta contiene el "cerebro" del proyecto: el modelo semántico en formato RDF/OWL.

## Contenido:
- **CLASE1.rdf**: La ontología completa en formato XML/RDF que define las clases (Actividad, Destino, Persona) y sus relaciones.
- **/mapeos/COMPLETO .json**: Reglas para transformar los datos CSV en individuos de la ontología mediante el plugin Cellfie de Protégé.

## Cómo usar:
1. Abrir `CLASE1.rdf` en Protégé para editar clases y relaciones.
2. Usar el archivo JSON en Cellfie para importar nuevos datos desde los archivos CSV.
