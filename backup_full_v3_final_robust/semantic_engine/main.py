from fastapi import FastAPI, Body, HTTPException
import rdflib
import os

app = FastAPI(title="Motor Semántico Caquetá V2.0 - SPARQL CRUD")

# Ruta flexible
RDF_PATH = "CLASE1.rdf" if os.path.exists("CLASE1.rdf") else "/data/ontologia/CLASE1.rdf"

g = rdflib.Graph()

def load_ontology():
    if os.path.exists(RDF_PATH):
        try:
            g.parse(RDF_PATH, format="xml")
            print(f"Ontología cargada. Total tripletas: {len(g)}")
        except Exception as e:
            print(f"Error cargando ontología: {e}")
    else:
        print(f"ADVERTENCIA: No se encontró el archivo en {RDF_PATH}")

load_ontology()

@app.post("/sparql")
async def sparql_query(payload: dict = Body(...)):
    query_str = payload.get("query")
    if not query_str:
        raise HTTPException(status_code=400, detail="No se proporcionó consulta")
    
    try:
        # Detectar si es una consulta de actualización (INSERT, DELETE, etc)
        if any(keyword in query_str.upper() for keyword in ["INSERT", "DELETE", "UPDATE"]):
            g.update(query_str)
            # Persistir cambios en el archivo físico
            g.serialize(destination=RDF_PATH, format="xml")
            return {"status": "success", "message": "Ontología actualizada y guardada"}
        
        # Consulta de selección normal
        results = g.query(query_str)
        lista = []
        for row in results:
            item = {}
            for i, var in enumerate(results.vars):
                val = row[i]
                item[str(var)] = str(val)
            lista.append(item)
        return lista
    except Exception as e:
        print(f"Error SPARQL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def status():
    return {"status": "online", "tripletas": len(g), "file": RDF_PATH}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3030)
