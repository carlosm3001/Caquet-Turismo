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
from datetime import datetime, timedelta

app = FastAPI(title="Amazonia-IA V3.9 - Hybrid Intelligence")

class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"): request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_ultra_safe_secret_999")
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
        if municipio and municipio.lower() not in m_uri: continue
        if categoria and categoria.lower() not in t_uri: continue
        if s_name not in seen:
            lista.append({"id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), "imagen": row.get("img", "")})
            seen.add(s_name)
    return lista

@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    if user_id not in chat_context: chat_context[user_id] = {"history": [], "suggested": [], "mun": None, "cat": None}
    ctx = chat_context[user_id]
    
    # 1. Detectar intención en el texto
    muns = ["florencia", "morelia", "doncello", "belen"]
    cats = {"cascada": ["cascada", "chorro"], "alojamiento": ["hotel", "dormir", "alojamiento"]}
    for m in muns: 
        if m in text: ctx["mun"] = m
    for c, aliases in cats.items():
        if any(a in text for a in aliases): ctx["cat"] = c

    # 2. Obtener datos reales
    sitios = await get_actividades(municipio=ctx["mun"], categoria=ctx["cat"])
    random.shuffle(sitios)
    
    # 3. Lógica de respuesta (LLM o Fallback Inteligente)
    if llm_model:
        try:
            data_str = "\n".join([f"- {s['id']} en {s['municipio']}" for s in sitios[:10]])
            prompt = f"Eres Amazonia-IA. Datos reales: {data_str}. Responde a: {text}. Sé humano y no repitas."
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass

    # 4. Fallback Inteligente (SIEMPRE responde algo útil basado en los datos)
    if sitios:
        # Buscamos uno que no hayamos sugerido
        rec = sitios[0]
        for s in sitios:
            if s['id'] not in ctx["suggested"]:
                rec = s
                break
        ctx["suggested"].append(rec['id'])
        
        if ctx["mun"] and ctx["cat"]:
            return {"reply": f"¡Claro! En {ctx['mun'].capitalize()} tengo {len(sitios)} opciones de {ctx['cat']}. Te sugiero conocer **{rec['id']}**. ¿Te cuento los detalles?"}
        if ctx["mun"]:
            return {"reply": f"He encontrado {len(sitios)} tesoros en {ctx['mun'].capitalize()}. ¿Buscas una cascada o un sitio para dormir?"}
        
        return {"reply": f"¡Hola! He encontrado {len(sitios)} sitios en el Caquetá. Por ejemplo, en {rec['municipio']} puedes visitar **{rec['id']}**. ¿Qué municipio te interesa?"}

    return {"reply": "Vaya, no encontré nada con esos datos. ¿Probamos buscando en Florencia o Morelia?"}

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", str(request.url_for('google_auth_callback')).replace("http://", "https://") if os.getenv("VERCEL") else request.url_for('google_auth_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if user_info['email'] not in users_db: users_db[user_info['email']] = {"role": "turista", "name": user_info['name']}
        jwt_token = jwt.encode({"email": user_info['email'], "role": "turista", "name": user_info['name'], "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        return HTMLResponse(content=f"<html><script>window.location.replace('/?token={jwt_token}');</script></html>")
    except: return RedirectResponse(url="/")

@app.get("/")
async def root(): return {"status": "V3.9 Hybrid Active"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
