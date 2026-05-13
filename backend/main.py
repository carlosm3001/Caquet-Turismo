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

app = FastAPI(title="Amazonia-IA V3.6 - CSRF Shield Fixed")

# --- SOLUCIÓN CRÍTICA PARA VERCEL (HTTPS Proxy) ---
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"):
            # Forzamos al sistema a creer que es HTTPS para que OAuth no falle
            request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_ultra_safe_secret_999")
ALGORITHM = "HS256"

# Configuración de Sesión para Nube (Lax es necesario para redirecciones de Google)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=True if os.getenv("VERCEL") else False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql"))
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

llm_model = None
try:
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_KEY:
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

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    # Usamos la URL configurada en Vercel como prioridad máxima
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
        # Mostramos un error amigable si el CSRF falla, pero con opción de reintento
        return HTMLResponse(content=f"""
            <div style="font-family:sans-serif; text-align:center; padding:50px;">
                <h2>Aviso de Seguridad</h2>
                <p>La sesión expiró por seguridad (CSRF). Por favor, intenta de nuevo.</p>
                <a href="/" style="background:#059669; color:white; padding:10px 20px; border-radius:10px; text-decoration:none;">REINTENTAR LOGIN</a>
            </div>
        """)

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img WHERE {{ ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri . ?sitio rdf:type ?tipo_uri . FILTER(?tipo_uri != owl:NamedIndividual && ?tipo_uri != owl:Class) OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }} }}"
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    for row in results:
        s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
        if municipio and municipio.lower() not in row.get("mun_uri", "").lower(): continue
        if s_name not in seen:
            lista.append({"id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), "imagen": row.get("img", "")})
            seen.add(s_name)
    return lista

@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    if llm_model:
        try:
            sitios = await get_actividades()
            resumen = "\n".join([f"- {s['id']} en {s['municipio']}" for s in sitios[:10]])
            prompt = f"Eres un guía del Caquetá. Datos: {resumen}. Responde amable a: {text}"
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass
    return {"reply": "¡Hola! ¿A qué parte del Caquetá te gustaría ir hoy?"}

@app.get("/")
async def read_root(): return {"status": "V3.6 CSRF Fixed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
