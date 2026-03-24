from flask import Flask, jsonify, request, render_template
import rdflib
import traceback
import time

app = Flask(__name__)

g = rdflib.Graph()
print("Cargando ontología... espera.")
g.parse("../ontologia/CLASE1.rdf", format="xml")

print("¡Lista para buscar!")

PREFIXES = """
PREFIX : <http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX uo3: <http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#>
"""

@app.route('/actividades', methods=['GET'])
def get_actividades():
    try:
        start_time = time.time()
        municipio_filtro = request.args.get('municipio', '').strip()
        
        query_body = """
        SELECT DISTINCT ?sitio ?tipo ?mun ?dificultad
        WHERE {
          ?sitio uo3:ubicadaEn ?mun_uri .
          ?sitio rdf:type ?type .
          FILTER(?type != <http://www.w3.org/2002/07/owl#NamedIndividual>)
          OPTIONAL { ?sitio uo3:nivelDificultad ?dificultad . }
          
          BIND(STRAFTER(STR(?mun_uri), "#") AS ?mun)
          BIND(STRAFTER(STR(?type), "#") AS ?tipo)
        """
        
        if municipio_filtro:
            limpio = municipio_filtro.replace(" ", "").replace('"', "")
            query_body += f'  FILTER(regex(?mun, "{limpio}", "i"))'
        
        query_body += "\n} LIMIT 60"
        
        results = g.query(PREFIXES + query_body)
        
        lista = []
        for row in results:
            lista.append({
                "id": str(row.sitio).split("#")[-1],
                "categoria": str(row.tipo),
                "municipio": str(row.mun),
                "dificultad": str(row.dificultad) if row.dificultad else "N/A"
            })
        
        print(f"Búsqueda '{municipio_filtro}' completada en {time.time() - start_time:.2f}s")
        return jsonify(lista)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
