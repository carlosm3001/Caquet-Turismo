import rdflib
import sys
import os

def ejecutar_consulta(sparql_query):
    g = rdflib.Graph()
    
    # Detectar la ruta absoluta del archivo RDF
    base_dir = os.path.dirname(os.path.abspath(__file__))
    RDF_PATH = os.path.join(base_dir, "..", "ontologia", "CLASE1.rdf")
    
    print(f"Cargando ontología desde {RDF_PATH}...")
    try:
        g.parse(RDF_PATH, format="xml")
        print("¡Ontología cargada con éxito!\n")
        
        results = g.query(sparql_query)
        
        # Imprimir encabezados dinámicamente
        vars = results.vars
        header = " | ".join([f"{str(v):<20}" for v in vars])
        print(header)
        print("-" * len(header))
        
        # Imprimir filas
        for row in results:
            line = " | ".join([f"{str(val).split('#')[-1]:<20}" for val in row])
            print(line)
            
        print(f"\nTotal de resultados: {len(results)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("="*60)
    print("CONSULTA 1: CONTEO DE SITIOS POR MUNICIPIO")
    print("="*60)
    q1 = """
    PREFIX : <http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#>
    SELECT ?municipio (COUNT(?sitio) AS ?total)
    WHERE {
      ?sitio :ubicadaEn ?mun .
      BIND(REPLACE(STR(?mun), "^.*#", "") AS ?municipio)
    }
    GROUP BY ?municipio
    ORDER BY DESC(?total)
    """
    ejecutar_consulta(q1)

    print("\n" + "="*60)
    print("CONSULTA 2: SITIOS DE DIFICULTAD ALTA")
    print("="*60)
    q2 = """
    PREFIX : <http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#>
    SELECT ?sitio ?municipio ?categoria
    WHERE {
      ?sitio :nivelDificultad "Alto" .
      ?sitio :ubicadaEn ?mun .
      ?sitio <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?type .
      FILTER(?type != <http://www.w3.org/2002/07/owl#NamedIndividual>)
      BIND(REPLACE(STR(?mun), "^.*#", "") AS ?municipio)
      BIND(REPLACE(STR(?type), "^.*#", "") AS ?categoria)
    }
    LIMIT 5
    """
    ejecutar_consulta(q2)

    print("\n" + "="*60)
    print("CONSULTA 3: LISTADO DE CATEGORÍAS ÚNICAS")
    print("="*60)
    q3 = """
    SELECT DISTINCT ?categoria
    WHERE {
      ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?type .
      FILTER(STRSTARTS(STR(?type), "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"))
      BIND(REPLACE(STR(?type), "^.*#", "") AS ?categoria)
    }
    """
    ejecutar_consulta(q3)
