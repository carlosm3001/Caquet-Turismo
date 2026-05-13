from fastapi import FastAPI, Query, Body, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
import os
import random
import jwt
import httpx
import google.generativeai as genai
from datetime import datetime, timedelta

app = FastAPI(title="Amazonia-IA V3.0 - Generative Semantic Brain")

# --- CONFIGURACIÓN DE SERVICIOS ---
SEMANTIC_ENGINE_URL = os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql")
if os.getenv("VERCEL"):
    SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", SEMANTIC_ENGINE_URL)

BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"
SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_secret_key_123")
ALGORITHM = "HS256"

# --- CONFIGURACIÓN DE GEMINI (CEREBRO LLM) ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

app.add_middleware(SessionMiddleware, secret_key="session_secret_xyz_789", same_site="lax", https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"), 
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"), 
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

users_db = {"admin@gmail.com": {"password": "admin", "role": "admin", "name": "Administrador"}}
chat_context = {} 

async def query_semantic_engine(sparql_query: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=30.0)
            return response.json()
        except: return []

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img WHERE {{ ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri . ?sitio rdf:type ?tipo_uri . FILTER(?tipo_uri != owl:NamedIndividual && ?tipo_uri != owl:Class) OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }} }}"
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    for row in results:
        s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
        if municipio and municipio.lower() not in row.get("mun_uri", "").lower(): continue
        if categoria and categoria.lower() not in row.get("tipo_uri", "").lower(): continue
        if s_name not in seen:
            lista.append({"id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), "imagen": row.get("img", "")})
            seen.add(s_name)
    return lista

# --- IA GENERATIVA SEMÁNTICA (V3.0) ---
@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    if user_id not in chat_context: chat_context[user_id] = {"history": []}
    ctx = chat_context[user_id]
    
    # 1. Extraer datos reales de la Ontología para alimentar el cerebro
    sitios = await get_actividades()
    resumen_datos = "\n".join([f"- {s['id']} es un {s['categoria']} en {s['municipio']} (Clima: {s['clima']}, Dificultad: {s['dificultad']})" for s in sitios[:20]])

    # 2. Si hay API Key, usamos el Cerebro Generativo Real
    if model:
        try:
            prompt = f"""
            Eres Amazonia-IA, el guía turístico más apasionado y experto del departamento del Caquetá, Colombia.
            Tu personalidad es amable, culta y muy humana. NO eres un robot, eres un amigo local.
            
            CONOCIMIENTOS REALES (ONTOLOGÍA RDF):
            {resumen_datos}
            
            HISTORIAL DE CONVERSACIÓN:
            {ctx['history'][-5:]}
            
            PREGUNTA DEL USUARIO: "{text}"
            
            INSTRUCCIONES:
            1. Usa solo la información de los conocimientos reales si el usuario pregunta por sitios.
            2. Si no tienes el dato, invita a explorar Florencia o Morelia de forma amigable.
            3. Sé variado, nunca repitas la misma frase.
            4. Si el usuario te saluda, responde con calidez amazónica.
            """
            response = model.generate_content(prompt)
            reply = response.text
            ctx["history"].append(f"Usuario: {text} | IA: {reply}")
            return {"reply": reply}
        except Exception as e:
            print(f"Error Gemini: {e}")

    # 3. Fallback inteligente (Modo sin API Key pero con lógica mejorada)
    saludos = ["¡Hola! El Caquetá te saluda.", "¡Claro que sí!", "Excelente pregunta."]
    if any(m in text for m in ["florencia", "morelia", "doncello"]):
        mun = [m for m in ["florencia", "morelia", "doncello"] if m in text][0]
        results = await get_actividades(municipio=mun)
        rec = random.choice(results)
        return {"reply": f"¡Qué bien que te interese {mun.capitalize()}! Es una zona increíble. Por ejemplo, te sugiero visitar **{rec['id']}**, es de tipo {rec['categoria']}. ¿Te cuento los detalles técnicos?"}
    
    return {"reply": f"{random.choice(saludos)} Soy tu guía del Caquetá. ¿Qué municipio te gustaría que exploremos juntos hoy?"}

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    q = f"SELECT (COUNT(DISTINCT ?s) as ?c) WHERE {{ ?s <{BASE_PREFIX}ubicadaEn> ?m }}"
    res = await query_semantic_engine(q)
    return {"total_tripletas": res[0]['c'] if res else 0, "usuarios_activos": len(users_db)}

@app.post("/api/v1/actividades")
async def save_actividad(act: NuevaActividad):
    rdf_id = act.id.replace(" ", "_"); rdf_mun = act.municipio.replace(" ", "_")
    query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> INSERT DATA {{ <{BASE_PREFIX}{rdf_id}> rdf:type <{BASE_PREFIX}{act.categoria}> . <{BASE_PREFIX}{rdf_id}> <{BASE_PREFIX}ubicadaEn> <{BASE_PREFIX}{rdf_mun}> . <{BASE_PREFIX}{rdf_id}> <{BASE_PREFIX}hasImageURL> '{act.imagen}' . }}"
    await query_semantic_engine(query)
    return {"status": "ok"}

@app.get("/")
async def read_index(): return {"message": "API V3.0 Generativa activa"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
