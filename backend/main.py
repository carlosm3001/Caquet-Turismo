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

app = FastAPI(title="Amazonia-IA V3.3 - Production Shield")

# --- CONFIGURACIÓN DE SERVICIOS ---
SEMANTIC_ENGINE_URL = os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql")
if os.getenv("VERCEL"):
    SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", SEMANTIC_ENGINE_URL)

BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"
SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_secret_key_123")
ALGORITHM = "HS256"

# --- CONFIGURACIÓN DE GEMINI ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        llm_model = genai.GenerativeModel('gemini-1.5-flash')
    except: llm_model = None
else:
    llm_model = None

# Middleware de Sesión (Necesario para OAuth)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- CONFIGURACIÓN GOOGLE OAUTH ---
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
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=35.0)
            if response.status_code == 200:
                return response.json()
        except: pass
        return []

class NuevaActividad(BaseModel):
    id: str
    categoria: str
    municipio: str
    imagen: str = ""

# --- ENDPOINTS DE AUTENTICACIÓN (BLINDADOS) ---

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    # Forzamos HTTPS en Vercel para evitar el Error 500 de Authlib
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        url = request.url_for('google_auth_callback')
        redirect_uri = str(url).replace("http://", "https://") if os.getenv("VERCEL") else str(url)
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        email = user_info['email']
        if email not in users_db:
            users_db[email] = {"role": "turista", "name": user_info['name']}
        
        jwt_token = jwt.encode({
            "email": email, "role": users_db[email]["role"], "name": users_db[email]["name"],
            "exp": datetime.utcnow() + timedelta(hours=24)
        }, SECRET_KEY, algorithm=ALGORITHM)
        
        target_url = "/?token=" + jwt_token if os.getenv("VERCEL") else f"http://localhost/?token={jwt_token}"
        return HTMLResponse(content=f"<html><script>window.location.replace('{target_url}');</script></html>")
    except Exception as e:
        return HTMLResponse(content=f"<h2>Error de Autenticación</h2><p>{str(e)}</p><a href='/'>Volver</a>", status_code=500)

# --- ENDPOINTS DE DATOS ---

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img
    WHERE {{
      ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri .
      ?sitio rdf:type ?tipo_uri .
      FILTER(?tipo_uri != <http://www.w3.org/2002/07/owl#NamedIndividual> && ?tipo_uri != <http://www.w3.org/2002/07/owl#Class>)
      OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }}
      OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }}
      OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }}
    }}
    """
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    for row in results:
        s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
        if municipio and municipio.lower() not in row.get("mun_uri", "").lower(): continue
        if categoria and categoria.lower() not in row.get("tipo_uri", "").lower(): continue
        if s_name not in seen:
            lista.append({
                "id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], 
                "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), 
                "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), 
                "imagen": row.get("img", "")
            })
            seen.add(s_name)
    return lista

@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    if user_id not in chat_context: chat_context[user_id] = {"history": []}
    ctx = chat_context[user_id]
    
    sitios = await get_actividades()
    resumen_datos = "\n".join([f"- {s['id']} en {s['municipio']} ({s['categoria']})" for s in sitios[:12]])

    if llm_model:
        try:
            prompt = f"Eres Amazonia-IA, un guía experto y humano del Caquetá. Usa estos datos reales:\n{resumen_datos}\nResponde amablemente a: {text}"
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass
    return {"reply": "¡Hola! Soy tu guía. ¿Quieres explorar las maravillas del Caquetá hoy?"}

@app.get("/")
async def read_root(): return {"status": "V3.3 Active"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
