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

app = FastAPI(title="Amazonia-IA V3.7 - Ultimate Auth Fix")

# --- CONFIGURACIÓN DE SEGURIDAD ---
SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_mega_safe_999")
ALGORITHM = "HS256"

# Configuración de Sesión Optimizada para Vercel
# Usamos same_site="lax" y desactivamos https_only temporalmente para asegurar la compatibilidad del estado
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- SERVICIOS ---
SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql"))
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

# IA Gemini
llm_model = None
try:
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        llm_model = genai.GenerativeModel('gemini-1.5-flash')
except: pass

# OAuth
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

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    # Forzamos HTTPS manualmente en la URL de redirección
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        url = request.url_for('google_auth_callback')
        redirect_uri = str(url).replace("http://", "https://") if os.getenv("VERCEL") else str(url)
    
    # IMPORTANTE: Authlib guardará el 'state' en la cookie de sesión aquí
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        # Intentamos obtener el token. Si falla el CSRF, aquí es donde salta el error.
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        email = user_info['email']
        
        if email not in users_db:
            users_db[email] = {"role": "turista", "name": user_info['name']}
        
        jwt_token = jwt.encode({
            "email": email, "role": users_db[email]["role"], "name": users_db[email]["name"],
            "exp": datetime.utcnow() + timedelta(hours=24)
        }, SECRET_KEY, algorithm=ALGORITHM)
        
        target_url = "/?token=" + jwt_token
        return HTMLResponse(content=f"<html><script>window.location.replace('{target_url}');</script></html>")
    
    except Exception as e:
        # Si falla, damos una opción de reintento directo que limpie la sesión
        return HTMLResponse(content=f"""
            <body style="font-family:sans-serif; text-align:center; padding:100px; background:#f0fdf4;">
                <h1 style="color:#065f46;">🔄 Sincronizando Acceso...</h1>
                <p style="color:#166534;">Por seguridad, Google requiere refrescar la sesión.</p>
                <a href="/api/v1/auth/google" style="background:#10b981; color:white; padding:15px 30px; border-radius:50px; text-decoration:none; font-weight:bold; box-shadow:0 10px 20px rgba(0,0,0,0.1);">CONTINUAR AL PORTAL</a>
                <p style="margin-top:20px; font-size:10px; color:#94a3b8;">Ref: {str(e)}</p>
            </body>
        """)

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img WHERE {{ ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri . ?sitio rdf:type ?tipo_uri . FILTER(?tipo_uri != owl:NamedIndividual && ?tipo_uri != owl:Class) OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }} }}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(SEMANTIC_ENGINE_URL, json={"query": query}, timeout=30.0)
            results = resp.json() if resp.status_code == 200 else []
        except: results = []
        
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
            prompt = f"Eres un guía del Caquetá. Datos reales: {resumen}. Responde amable y breve a: {text}"
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass
    return {"reply": "¡Hola! ¿A qué parte del Caquetá quieres ir?"}

@app.get("/")
async def root(): return {"status": "V3.7 Final"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
