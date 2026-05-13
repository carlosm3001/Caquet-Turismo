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
from datetime import datetime, timedelta

app = FastAPI(title="Plataforma Caquetá V2.2 - IA con Memoria")

# --- CONFIGURACIÓN DE SERVICIOS ---
SEMANTIC_ENGINE_URL = os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql")
if os.getenv("VERCEL"):
    SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", SEMANTIC_ENGINE_URL)

BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"
SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_secret_key_123")
ALGORITHM = "HS256"

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

class NuevaActividad(BaseModel):
    id: str
    categoria: str
    municipio: str
    imagen: str = ""

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        email = user_info['email']
        if email not in users_db:
            users_db[email] = {"role": "turista", "name": user_info['name']}
        jwt_token = jwt.encode({"email": email, "role": users_db[email]["role"], "name": users_db[email]["name"], "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm=ALGORITHM)
        target_url = "/?token=" + jwt_token if os.getenv("VERCEL") else f"http://localhost/?token={jwt_token}"
        return HTMLResponse(content=f"<html><script>window.location.replace('{target_url}');</script></html>")
    except: return RedirectResponse(url="/?error=auth")

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

# --- IA CON APRENDIZAJE Y MEMORIA (V5.0) ---
@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    
    if user_id not in chat_context: 
        chat_context[user_id] = {"mun": None, "cat": None, "history": [], "favorites": []}
    
    ctx = chat_context[user_id]
    ctx["history"].append(text)

    # APRENDIZAJE: Detectar gustos
    if "me gusta" in text or "amo" in text:
        for m in ["florencia", "morelia", "doncello"]:
            if m in text:
                ctx["favorites"].append(m)
                return {"reply": f"¡Anotado! He guardado en mi memoria semántica que te gusta **{m.capitalize()}**. De ahora en adelante, priorizaré mis recomendaciones sobre esa zona. ¿Quieres que veamos qué hay de nuevo allí?"}

    # Detección de municipio
    muns = ["florencia", "morelia", "doncello", "belen", "san vicente", "puerto rico"]
    for m in muns:
        if m in text: 
            if ctx["mun"] == m: # Si repite el municipio, cambiamos la respuesta
                results = await get_actividades(municipio=m)
                rec = random.choice(results)
                return {"reply": f"¡Veo que te apasiona {m.capitalize()}! Ya sabemos que hay muchos sitios allí, pero ¿qué te parece si exploramos específicamente **{rec['id']}**?"}
            ctx["mun"] = m

    # Detección de categorías
    cats_map = {"Cascada": ["cascada", "chorro"], "Alojamiento": ["hotel", "dormir"], "CaminataEcologica": ["caminata", "senderismo"]}
    for official, aliases in cats_map.items():
        if any(alias in text for alias in aliases): ctx["cat"] = official

    # RESPUESTA BASADA EN CONTEXTO
    results = await get_actividades(municipio=ctx["mun"], categoria=ctx["cat"])
    
    if not results:
        return {"reply": "Aún estoy aprendiendo sobre esa combinación. ¿Por qué no probamos buscando solo por el municipio?"}

    # Evitar repetición usando el historial
    rec = results[0]
    for r in results:
        if r['id'].lower() not in [h.lower() for h in ctx["history"]]:
            rec = r
            break

    if ctx["mun"] and ctx["cat"]:
        return {"reply": f"¡Tengo nuevas ideas para ti! En {ctx['mun'].capitalize()} hay {len(results)} opciones de {ctx['cat']}. Te sugiero conocer **{rec['id']}**. ¿Te cuento los detalles técnicos?"}
    
    if ctx["mun"]:
        return {"reply": f"En {ctx['mun'].capitalize()} he mapeado {len(results)} maravillas. ¿Buscas una aventura en cascadas o quizás un sitio para descansar?"}

    return {"reply": "¡Hola! Soy tu guía amazónico. ¿Qué parte del Caquetá te gustaría descubrir hoy?"}

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    q = f"SELECT (COUNT(DISTINCT ?s) as ?c) WHERE {{ ?s <{BASE_PREFIX}ubicadaEn> ?m }}"
    res = await query_semantic_engine(q)
    total = res[0]['c'] if res else 0
    return {"total_tripletas": total, "usuarios_activos": len(users_db)}

@app.post("/api/v1/actividades")
async def save_actividad(act: NuevaActividad):
    rdf_id = act.id.replace(" ", "_")
    rdf_mun = act.municipio.replace(" ", "_")
    query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> INSERT DATA {{ <{BASE_PREFIX}{rdf_id}> rdf:type <{BASE_PREFIX}{act.categoria}> . <{BASE_PREFIX}{rdf_id}> <{BASE_PREFIX}ubicadaEn> <{BASE_PREFIX}{rdf_mun}> . <{BASE_PREFIX}{rdf_id}> <{BASE_PREFIX}hasImageURL> '{act.imagen}' . }}"
    await query_semantic_engine(query)
    return {"status": "ok"}

@app.get("/")
async def read_index(): return {"message": "API V2.2 activa"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
