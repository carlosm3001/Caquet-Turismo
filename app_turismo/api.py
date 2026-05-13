from flask import Flask, jsonify, request, render_template
import rdflib
import traceback

import os

app = Flask(__name__)

g = rdflib.Graph()
# Detectar la ruta absoluta del archivo RDF relativa a este script
base_dir = os.path.dirname(os.path.abspath(__file__))
RDF_PATH = os.path.join(base_dir, "..", "ontologia", "CLASE1.rdf")

print(f"Cargando ontología desde {RDF_PATH}...")
try:
    g.parse(RDF_PATH, format="xml")
    print("¡Base de datos cargada!")
except Exception as e:
    print(f"ERROR: {e}")

BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

@app.route('/actividades', methods=['GET'])
def get_actividades():
    try:
        mun = request.args.get('municipio', '').strip()
        cat = request.args.get('categoria', '').strip()
        
        # Consulta base
        query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?email
        WHERE {{
          ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri .
          ?sitio rdf:type ?tipo_uri .
          FILTER(?tipo_uri != <http://www.w3.org/2002/07/owl#NamedIndividual>)
          OPTIONAL {{ ?sitio <{BASE_PREFIX}email> ?email . }}
          OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }}
          OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }}
        }}
        """
        results = g.query(query)
        lista = []
        for row in results:
            m_name = str(row.mun_uri).split("#")[-1]
            t_name = str(row.tipo_uri).split("#")[-1]
            
            # Filtro manual para mayor precisión
            if mun and mun.lower() not in m_name.lower(): continue
            if cat and cat.lower() not in t_name.lower(): continue
            
            lista.append({
                "id": str(row.sitio).split("#")[-1],
                "categoria": t_name,
                "municipio": m_name.replace("_", " "),
                "clima": str(row.clima) if row.clima else "Cálido",
                "dificultad": str(row.dif) if row.dif else "N/A",
                "email": str(row.email) if row.email else "info@caqueta.com"
            })
        return jsonify(lista)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/municipios', methods=['GET'])
def get_municipios():
    try:
        # Buscamos TODO lo que sea un destino o esté vinculado a una ubicación
        query = f"""
        SELECT DISTINCT ?m
        WHERE {{
          {{ ?m <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{BASE_PREFIX}Destino> }}
          UNION
          {{ ?s <{BASE_PREFIX}ubicadaEn> ?m }}
        }}
        """
        results = g.query(query)
        lista = []
        seen = set()
        
        for row in results:
            nombre_raw = str(row.m).split("#")[-1]
            if not nombre_raw or nombre_raw.lower() == "destino" or nombre_raw in seen: continue
            
            seen.add(nombre_raw)
            lista.append({
                "nombre": nombre_raw.replace("_", " "),
                "clima": "Tropical",
                "total_actividades": "Ver"
            })
        
        return jsonify(sorted(lista, key=lambda x: x['nombre']))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
