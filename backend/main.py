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
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=30.0)
            return response.json() if response.status_code == 200 else []
        except: return []

# --- ENDPOINTS DE AUTENTICACIÓN (RESTAURADOS) ---

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
        jwt_token = jwt.encode({"email": email, "name": user_info['name'], "role": "turista", "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        target_url = "/?token=" + jwt_token
        return HTMLResponse(content=f"<html><script>window.location.replace('{target_url}');</script></html>")
    except Exception as e:
        return RedirectResponse(url="/?error=auth_failed")

# --- ENDPOINTS DE DATOS ---

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX owl: <http://www.w3.org/2002/07/owl#> SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif ?img WHERE {{ ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri . ?sitio rdf:type ?tipo_uri . FILTER(?tipo_uri != owl:NamedIndividual && ?tipo_uri != owl:Class) OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }} OPTIONAL {{ ?sitio <{BASE_PREFIX}hasImageURL> ?img . }} }}"
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    blacklist = ["bitchip", "wrapsafe", "fintone", "span", "ronstring", "prodder", "hatity", "flexidy", "bigtax"]
    for row in results:
        s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
        if any(bad in s_name.lower() for bad in blacklist): continue
        if municipio and municipio.lower() not in row.get("mun_uri", "").lower(): continue
        if s_name not in seen:
            lista.append({"id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), "clima": row.get("clima", "Cálido"), "dificultad": row.get("dif", "Media"), "imagen": row.get("img", "")})
            seen.add(s_name)
    return lista

@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    if user_id not in chat_context: chat_context[user_id] = {"suggested": [], "last_rec": None}
    ctx = chat_context[user_id]
    
    if any(w in text for word in ["detalle", "cuentame", "info"]):
        if ctx["last_rec"]:
            s = ctx["last_rec"]
            return {"reply": f"¡Claro! **{s['id']}** es un lugar de tipo {s['categoria']} en {s['municipio']}. Clima {s['clima']} y dificultad {s['dificultad']}."}

    muns = ["florencia", "morelia", "doncello", "belen"]
    mun = next((m for m in muns if m in text), None)
    sitios = await get_actividades(municipio=mun)
    random.shuffle(sitios)
    
    if llm_model:
        try:
            prompt = f"Eres Amazonia-IA, un guía experto. Datos: {sitios[:10]}. Usuario: {text}. Responde amigable."
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass

    if sitios:
        rec = sitios[0]
        ctx["last_rec"] = rec
        return {"reply": f"¡Hola! Encontré sitios geniales. Te sugiero conocer **{rec['id']}** en {rec['municipio']}. ¿Te cuento más detalles?"}
    
    return {"reply": "¡Hola! ¿A qué parte del Caquetá te gustaría ir hoy?"}

class LoginRequest(BaseModel):
    email: str
    password: str

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

@app.get("/status")
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
