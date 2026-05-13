from fastapi import FastAPI, Query, Body, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os
import random
import jwt
import httpx
import google.generativeai as genai
import re
from datetime import datetime, timedelta

app = FastAPI(title="Amazonia-IA V4.1 - Real Data Filter & Smart Guide")

class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"): request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_safe_2026")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql"))
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

llm_model = None
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        llm_model = genai.GenerativeModel('gemini-1.5-flash')
    except: pass

oauth = OAuth()
if os.getenv("GOOGLE_CLIENT_ID"):
    oauth.register(
        name='google', client_id=os.getenv("GOOGLE_CLIENT_ID"), 
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
            return response.json() if response.status_code == 200 else []
        except: return []

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img WHERE {{ ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri . ?sitio rdf:type ?tipo_uri . FILTER(?tipo_uri != owl:NamedIndividual && ?tipo_uri != owl:Class) OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }} }}"
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    
    for row in results:
        s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
        m_uri = row.get("mun_uri", "").lower()
        t_uri = row.get("tipo_uri", "").lower()
        
        # --- FILTRO DE CALIDAD AVANZADO ---
        # 1. Ignorar nombres sospechosos de ser generados (Sin espacios, sin guiones, palabras cortas raras)
        if not "_" in row.get("sitio", "") and not " " in s_name and len(s_name) < 10 and s_name[0].isupper():
            # Excepción para nombres reales cortos si existieran, pero "Bigtax" etc caen aquí
            if not any(word in s_name.lower() for word in ["hotel", "posada", "finca", "cascada"]):
                continue

        if municipio and municipio.lower() not in m_uri: continue
        if categoria and categoria.lower() not in t_uri: continue
        
        if s_name not in seen:
            lista.append({
                "id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], 
                "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), 
                "clima": row.get("clima", "Cálido Tropical"), "dificultad": row.get("dif", "Media"), 
                "imagen": row.get("img", "")
            })
            seen.add(s_name)
    
    # Priorizar nombres con "_" (los que nosotros creamos)
    lista.sort(key=lambda x: "_" in x["id"], reverse=True)
    return lista

# --- IA EXPERTA V4.1 ---
@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    if user_id not in chat_context: chat_context[user_id] = {"history": [], "suggested": [], "mun": None, "cat": None, "last_rec": None}
    ctx = chat_context[user_id]
    
    # 1. INTENCIÓN: DETALLES O OTRO LUGAR
    if any(word in text for word in ["detalle", "más información", "cuentame", "como es"]):
        if ctx["last_rec"]:
            s = ctx["last_rec"]
            return {"reply": f"¡Claro! **{s['id']}** es un sitio de tipo {s['categoria']} en {s['municipio']}. El clima es {s['clima']} y su acceso es de dificultad {s['dificultad']}. ¿Buscamos otro sitio o quieres cambiar de municipio?"}
        return {"reply": "Me encantaría darte detalles, pero primero dime qué lugar o municipio te interesa."}

    # 2. INTENCIÓN: OTRO LUGAR (Rompe el bucle)
    if any(word in text for word in ["otro", "otra", "diferente", "siguiente"]):
        sitios = await get_actividades(municipio=ctx["mun"], categoria=ctx["cat"])
        # Filtramos los ya sugeridos
        nuevos = [s for s in sitios if s['id'] not in ctx["suggested"]]
        if nuevos:
            rec = nuevos[0]
            ctx["suggested"].append(rec['id'])
            ctx["last_rec"] = rec
            return {"reply": f"¡Entendido! Aquí tienes otra opción: **{rec['id']}** en {rec['municipio']}. ¿Quieres que te cuente cómo es este lugar?"}
        return {"reply": "He explorado todas mis opciones actuales en esa zona. ¿Qué tal si probamos en otro municipio?"}

    # 3. DETECTAR MUNICIPIO Y CATEGORÍA
    muns = ["florencia", "morelia", "doncello", "belen", "san vicente"]
    cats_map = {"cascada": ["cascada", "chorro"], "alojamiento": ["hospedaje", "dormir", "hotel", "posada", "estadia"]}
    
    for m in muns: 
        if m in text: 
            if ctx["mun"] != m: ctx["suggested"] = [] # Limpiar sugeridos al cambiar municipio
            ctx["mun"] = m
    for cat_id, aliases in cats_map.items():
        if any(a in text for a in aliases): 
            if ctx["cat"] != cat_id: ctx["suggested"] = []
            ctx["cat"] = cat_id

    # 4. OBTENER DATOS Y RESPONDER
    sitios = await get_actividades(municipio=ctx["mun"], categoria=ctx["cat"])
    
    if llm_model:
        try:
            prompt = f"Eres Amazonia-IA, guía experto. Datos: {sitios[:10]}. Usuario: {text}. Responde amigable y sugiere un sitio. No repitas."
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass

    if sitios:
        rec = sitios[0]
        ctx["suggested"].append(rec['id'])
        ctx["last_rec"] = rec
        if ctx["mun"] and ctx["cat"]:
            return {"reply": f"¡Qué bien! En {ctx['mun'].capitalize()} encontré {len(sitios)} sitios de {ctx['cat']}. Te sugiero conocer **{rec['id']}**. ¿Te cuento los detalles técnicos?"}
        if ctx["mun"]:
            return {"reply": f"En {ctx['mun'].capitalize()} hay {len(sitios)} tesoros registrados. ¿Buscas una cascada o un sitio para pasar la noche?"}
        
    return {"reply": "¡Hola! Soy tu guía del Caquetá. ¿A qué municipio te gustaría que viajáramos hoy?"}

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        jwt_token = jwt.encode({"email": user_info['email'], "name": user_info['name'], "role": "turista", "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        return HTMLResponse(content=f"<html><script>window.location.replace('/?token={jwt_token}');</script></html>")
    except: return RedirectResponse(url="/")

@app.get("/")
async def root(): return {"status": "V4.1 Smart Filter Active"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
