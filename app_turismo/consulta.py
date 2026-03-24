import rdflib

g = rdflib.Graph()
print("Cargando datos del Caquetá...")
g.parse("CLASE1.rdf", format="xml")

# Consulta para ver el Tipo de Actividad y la Dificultad
query = """
PREFIX : <http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX uo3: <http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#>

SELECT DISTINCT ?sitio ?tipo ?municipio ?dificultad
WHERE {
  ?sitio uo3:ubicadaEn ?mun .
  ?sitio rdf:type ?type .

  # Filtramos para que solo nos de las clases de turismo, no las técnicas de OWL
  FILTER(?type != <http://www.w3.org/2002/07/owl#NamedIndividual>)

  OPTIONAL { ?sitio uo3:nivelDificultad ?dificultad . }

  BIND(REPLACE(STR(?mun), "^.*#", "") AS ?municipio)
  BIND(REPLACE(STR(?type), "^.*#", "") AS ?tipo)
}
LIMIT 15
"""

print("-" * 85)
print(f"{'ID SITIO':<15} | {'CATEGORÍA':<20} | {'MUNICIPIO':<15} | {'DIFICULTAD'}")
print("-" * 85)

results = g.query(query)
for row in results:
    sitio = str(row.sitio).split("#")[-1]
    tipo = str(row.tipo)
    municipio = str(row.municipio)
    dificultad = str(row.dificultad) if row.dificultad else "N/A"

    print(f"{sitio:<15} | {tipo:<20} | {municipio:<15} | {dificultad}")

print("-" * 85)
print(f"Total de resultados: {len(results)}")