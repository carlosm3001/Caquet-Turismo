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

app = FastAPI(title="Amazonia-IA V4.2 - Auth Restored & Stable")

# --- PROXY PARA VERCEL (HTTPS) ---
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"): request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_safe_2026")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=True if os.getenv("VERCEL") else False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- CONFIGURACIÓN DE SERVICIOS ---
SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql"))
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

# --- IA GEMINI ---
llm_model = None
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        llm_model = genai.GenerativeModel('gemini-1.5-flash')
    except: pass

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

import json

# --- PERSISTENCIA DE USUARIOS ---
USERS_FILE = "/tmp/users.json" if os.getenv("VERCEL") else "users.json"
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f: return json.load(f)
    return {"admin@gmail.com": {"password": "admin", "role": "admin", "name": "Administrador"}}

def save_users(db):
    with open(USERS_FILE, "w") as f: json.dump(db, f)

users_db = load_users()

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

@app.post("/api/v1/register")
async def register(data: RegisterRequest):
    if data.email in users_db:
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    
    users_db[data.email] = {
        "password": data.password,
        "role": "turista",
        "name": data.name
    }
    save_users(users_db)
    
    token = jwt.encode({
        "email": data.email,
        "name": data.name,
        "role": "turista",
        "exp": datetime.utcnow() + timedelta(hours=24)
    }, SECRET_KEY, algorithm="HS256")
    
    return {"token": token}

@app.post("/api/v1/login")
async def login(data: LoginRequest):
    user = users_db.get(data.email)
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    token = jwt.encode({
        "email": data.email,
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.utcnow() + timedelta(hours=24)
    }, SECRET_KEY, algorithm="HS256")
    
    return {"token": token}

@app.get("/api/v1/status")
async def get_status():
    async with httpx.AsyncClient() as client:
        try:
            # Intentar despertar al motor semántico
            resp = await client.get(SEMANTIC_ENGINE_URL.replace("/sparql", "/status"), timeout=5.0)
            engine_status = resp.json() if resp.status_code == 200 else {"status": "offline"}
        except:
            engine_status = {"status": "error"}
    
    return {
        "status": "V4.2 Online",
        "semantic_engine": engine_status,
        "timestamp": datetime.utcnow()
    }

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    query = "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }"
    results = await query_semantic_engine(query)
    total = results[0].get("count", "0") if results else "0"
    return {"total_tripletas": total}

@app.post("/api/v1/actividades")
async def create_actividad(payload: dict = Body(...)):
    name = payload.get("id", "").replace(" ", "_")
    cat = payload.get("categoria", "Actividad")
    mun = payload.get("municipio", "Florencia").replace(" ", "_")
    img = payload.get("imagen", "")
    
    sparql_update = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    INSERT DATA {{
      <{BASE_PREFIX}{name}> rdf:type <{BASE_PREFIX}{cat}> .
      <{BASE_PREFIX}{name}> <{BASE_PREFIX}ubicadaEn> <{BASE_PREFIX}{mun}> .
      <{BASE_PREFIX}{name}> <{BASE_PREFIX}hasImageURL> "{img}" .
    }}
    """
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_update}, timeout=30.0)
            if response.status_code == 200:
                return {"status": "success", "message": f"Lugar {name} creado"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="Error al conectar con el motor semántico")

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>Amazonia-IA API Online</h1><p>Frontend no encontrado en /frontend/index.html</p></body></html>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
