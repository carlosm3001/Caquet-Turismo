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

app = FastAPI(title="Amazonia-IA V3.8 - Intelligent Memory")

# --- PROXY PARA VERCEL ---
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"): request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_ultra_safe_secret_999")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
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

# --- OAUTH ---
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
        if municipio and municipio.lower() not in row.get("mun_uri", "").lower(): continue
        if s_name not in seen:
            lista.append({"id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), "imagen": row.get("img", "")})
            seen.add(s_name)
    return lista

# --- IA CON MEMORIA REAL (V3.8) ---
@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    
    if user_id not in chat_context: chat_context[user_id] = {"history": [], "suggested": []}
    ctx = chat_context[user_id]
    
    sitios = await get_actividades()
    # Mezclamos para que no siempre vea los mismos 10 al inicio
    random.shuffle(sitios)
    
    # Filtramos sitios que ya sugerimos en esta sesión para no repetir
    sitios_frescos = [s for s in sitios if s['id'] not in ctx["suggested"]]
    if not sitios_frescos: 
        ctx["suggested"] = [] # Reset si ya recorrimos todos
        sitios_frescos = sitios

    resumen_datos = "\n".join([f"- {s['id']} en {s['municipio']} ({s['categoria']})" for s in sitios_frescos[:15]])

    if llm_model:
        try:
            prompt = f"""
            Eres Amazonia-IA, un guía humano y experto. 
            DATOS REALES: {resumen_datos}
            HISTORIAL: {ctx['history'][-4:]}
            
            INSTRUCCIÓN: 
            1. Responde a: "{text}" de forma variada y entusiasta.
            2. Si sugieres un sitio, asegúrate de que sea uno de los DATOS REALES.
            3. NO te repitas. Si ya hablaste de un sitio, busca otro.
            4. Sé muy breve (máximo 3 frases).
            """
            response = llm_model.generate_content(prompt)
            reply = response.text
            
            # Guardamos en memoria para no repetir
            for s in sitios_frescos:
                if s['id'].lower() in reply.lower():
                    ctx["suggested"].append(s['id'])
            
            ctx["history"].append(f"U: {text} | IA: {reply}")
            return {"reply": reply}
        except: pass

    # Fallback si no hay API Key o falla Gemini
    return {"reply": f"¡Hola! El Caquetá tiene {len(sitios)} maravillas. ¿Quieres conocer una cascada en Florencia o prefieres Morelia? (Pista: Añade tu GEMINI_API_KEY para una charla real)"}

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
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
        if email not in users_db: users_db[email] = {"role": "turista", "name": user_info['name']}
        jwt_token = jwt.encode({"email": email, "role": users_db[email]["role"], "name": users_db[email]["name"], "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        target_url = "/?token=" + jwt_token if os.getenv("VERCEL") else f"http://localhost/?token={jwt_token}"
        return HTMLResponse(content=f"<html><script>window.location.replace('{target_url}');</script></html>")
    except Exception as e:
        return RedirectResponse(url=f"/api/v1/auth/google")

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    q = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT (COUNT(DISTINCT ?s) as ?c) WHERE {{ ?s <{BASE_PREFIX}ubicadaEn> ?m }}"
    res = await query_semantic_engine(q)
    return {"total_tripletas": res[0]['c'] if res else 0, "usuarios_activos": len(users_db)}

@app.get("/")
async def root(): return {"status": "V3.8 Stable"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
