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
import json

app = FastAPI(title="Amazonia-IA V4.2 - Vercel Safe Mode")

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
    except Exception as e:
        print(f"IA Error: {e}")

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

# --- PERSISTENCIA DE USUARIOS ---
USERS_FILE = "/tmp/users.json" if os.getenv("VERCEL") else "users.json"
def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r") as f: return json.load(f)
    except Exception as e:
        print(f"Load Users Error: {e}")
    return {"admin@gmail.com": {"password": "admin", "role": "admin", "name": "Administrador"}}

def save_users(db):
    try:
        with open(USERS_FILE, "w") as f: json.dump(db, f)
    except Exception as e:
        print(f"Save Users Error: {e}")

users_db = load_users()
chat_context = {} 

async def query_semantic_engine(sparql_query: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=10.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Semantic Engine Offline: {e}")
    return []

# --- ENDPOINTS ---

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

@app.post("/api/v1/register")
async def register(data: RegisterRequest):
    try:
        if data.email in users_db:
            raise HTTPException(status_code=400, detail="El correo ya está registrado")
        users_db[data.email] = {"password": data.password, "role": "turista", "name": data.name}
        save_users(users_db)
        token = jwt.encode({"email": data.email, "name": data.name, "role": "turista", "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        return {"token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/login")
async def login(data: LoginRequest):
    try:
        user = users_db.get(data.email)
        if not user or user["password"] != data.password:
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        token = jwt.encode({"email": data.email, "name": user["name"], "role": user["role"], "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        return {"token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    try:
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not redirect_uri:
            url = request.url_for('google_auth_callback')
            redirect_uri = str(url).replace("http://", "https://") if os.getenv("VERCEL") else str(url)
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Redirect Error: {e}")

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        jwt_token = jwt.encode({"email": user_info['email'], "name": user_info['name'], "role": "turista", "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        return HTMLResponse(content=f"<html><script>window.location.replace('/?token={jwt_token}');</script></html>")
    except Exception as e:
        return RedirectResponse(url="/?error=auth_failed")

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None):
    try:
        query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img WHERE {{ ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri . ?sitio rdf:type ?tipo_uri . FILTER(?tipo_uri != owl:NamedIndividual && ?tipo_uri != owl:Class) OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }} }}"
        results = await query_semantic_engine(query)
        lista = []
        blacklist = ["bitchip", "wrapsafe", "fintone", "span", "ronstring", "prodder", "hatity", "flexidy", "bigtax"]
        for row in results:
            s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
            if any(bad in s_name.lower() for bad in blacklist): continue
            if municipio and municipio.lower() not in row.get("mun_uri", "").lower(): continue
            lista.append({"id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), "imagen": row.get("img", "")})
        return lista
    except Exception as e:
        print(f"Actividades Error: {e}")
        return []

@app.get("/api/v1/status")
async def get_status():
    try:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(SEMANTIC_ENGINE_URL.replace("/sparql", "/status"), timeout=5.0)
                engine_status = resp.json() if resp.status_code == 200 else {"status": "offline"}
            except: engine_status = {"status": "offline"}
        return {"status": "V4.2 Safe Mode", "semantic_engine": engine_status}
    except Exception as e:
        return {"status": "Error", "detail": str(e)}

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    try:
        query = "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }"
        results = await query_semantic_engine(query)
        total = results[0].get("count", "0") if results else "0"
        return {"total_tripletas": total}
    except: return {"total_tripletas": "0"}

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f: return f.read()
    return "<h1>API Online</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
