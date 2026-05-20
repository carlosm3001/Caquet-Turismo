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

app = FastAPI(title="Amazonia-IA V4.5 - Enhanced Semantic Data")

# --- PROXY PARA VERCEL (HTTPS) ---
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"): request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_safe_2026")
ALGORITHM = "HS256"

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

# --- PERSISTENCIA SIMPLIFICADA ---
users_db = {
    "admin@gmail.com": {"password": "admin", "role": "admin", "name": "Administrador Principal"}
}
chat_context = {}

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class ReservaRequest(BaseModel):
    lugar_id: str
    fecha_inicio: str
    personas: int
    dias: int
    user_email: str
    user_name: str

async def query_semantic_engine(sparql_query: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error consultando Motor Semántico: {e}")
            return []

def create_token(data: dict):
    payload = data.copy()
    payload.update({"exp": datetime.utcnow() + timedelta(hours=24)})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/api/v1/register")
async def register(data: RegisterRequest):
    users_db[data.email] = {"password": data.password, "role": "turista", "name": data.name}
    token = create_token({"email": data.email, "name": data.name, "role": "turista"})
    return {"token": token}

@app.post("/api/v1/login")
async def login(data: LoginRequest):
    u = users_db.get(data.email)
    if u and u["password"] == data.password:
        token = create_token({"email": data.email, "role": u["role"], "name": u["name"]})
        return {"token": token, "role": u["role"], "name": u["name"]}
    raise HTTPException(status_code=401, detail="Credenciales incorrectas")

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", request.url_for('google_auth_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info: raise HTTPException(status_code=400)
        
        email = user_info['email']
        if email not in users_db:
            users_db[email] = {"password": str(random.randint(1000,9999)), "role": "turista", "name": user_info['name']}
        
        u = users_db[email]
        jwt_token = create_token({"email": email, "role": u["role"], "name": u["name"]})
        target_url = "/?token=" + jwt_token if os.getenv("VERCEL") else f"http://localhost/?token={jwt_token}"
        return HTMLResponse(content=f"<script>window.location.replace('{target_url}');</script>")
    except Exception as e:
        return RedirectResponse(url="/?error=auth_failed")

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT DISTINCT ?sitio ?nombre ?tipo_uri ?mun_uri ?clima ?dif ?precio ?disp ?reserva ?desc ?horario
    WHERE {{
      ?sitio :ubicadaEn ?mun_uri .
      ?sitio rdf:type ?tipo_uri .
      FILTER(?tipo_uri != <http://www.w3.org/2002/07/owl#NamedIndividual> && ?tipo_uri != <http://www.w3.org/2002/07/owl#Class>)
      OPTIONAL {{ ?sitio :nombreActividad ?nombre . }}
      OPTIONAL {{ ?mun_uri :clima ?clima . }}
      OPTIONAL {{ ?sitio :nivelDificultad ?dif . }}
      OPTIONAL {{ ?sitio :precio ?precio . }}
      OPTIONAL {{ ?sitio :disponibilidad ?disp . }}
      OPTIONAL {{ ?sitio :reservaURL ?reserva . }}
      OPTIONAL {{ ?sitio :descripcion ?desc . }}
      OPTIONAL {{ ?sitio :horario ?horario . }}
    }}
    """
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    for row in results:
        s_uri = row.get("sitio", "")
        s_id = s_uri.split("#")[-1]
        if s_id in seen: continue
        
        m_uri = row.get("mun_uri", "")
        m_name = m_uri.split("#")[-1].replace("_", " ")
        t_uri = row.get("tipo_uri", "")
        t_name = t_uri.split("#")[-1]
        
        # Filtros
        if municipio and municipio.lower() not in m_name.lower(): continue
        if categoria and categoria.lower() not in t_name.lower(): continue
        
        # Limpieza de valores None o strings 'None'
        clima_val = row.get("clima")
        if not clima_val or clima_val == "None": clima_val = "Cálido Húmedo"
        
        dif_val = row.get("dif")
        if not dif_val or dif_val == "None": dif_val = "Media"
        
        precio_val = row.get("precio")
        try:
            if not precio_val or precio_val == "None": precio_val = 0
            else: precio_val = int(precio_val)
        except: precio_val = 0
            
        disp_val = row.get("disp")
        if not disp_val or disp_val == "None": disp_val = "Disponible"
        
        res_val = row.get("reserva")
        if not res_val or res_val == "None" or res_val == "#": res_val = "https://wa.me/573000000000"

        lista.append({
            "id": row.get("nombre") or s_id.replace("_", " "),
            "real_id": s_id,
            "categoria": t_name,
            "municipio": m_name,
            "clima": clima_val,
            "dificultad": dif_val,
            "precio": precio_val,
            "disponibilidad": disp_val,
            "reserva": res_val,
            "descripcion": row.get("desc") or "Explora la belleza natural inigualable de este destino en el Caquetá.",
            "horario": row.get("horario") or "Sujeto a disponibilidad y condiciones climáticas."
        })
        seen.add(s_id)
    return lista

@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    # Lógica de IA mejorada
    message = payload.get("message", "")
    # Aquí podrías integrar el llm_model si lo tienes configurado
    return {"reply": "Estoy procesando tu solicitud sobre el Caquetá. Por ahora, te recomiendo explorar la sección de destinos."}

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    query = "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }"
    results = await query_semantic_engine(query)
    total_rdf = results[0].get("count", "0") if results else "0"
    return {
        "total_tripletas": total_rdf,
        "total_usuarios": len(users_db),
        "status_motor": "online"
    }

@app.get("/api/v1/status")
async def get_status():
    return {"status": "online", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/v1/reservas")
async def post_reserva(res: ReservaRequest):
    res_id = f"Reserva_{int(datetime.utcnow().timestamp())}"
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    INSERT DATA {{
      :{res_id} rdf:type :Reserva ;
                :fechaInicio "{res.fecha_inicio}" ;
                :cantidadPersonas {res.personas} ;
                :cantidadDias {res.dias} ;
                :usuarioReserva "{res.user_email}" ;
                :lugarReservado "{res.lugar_id}" .
    }}
    """
    results = await query_semantic_engine(query)
    return {"status": "success", "id": res_id}

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f: return f.read()
    return "<h1>API Online</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
