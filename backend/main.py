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
from datetime import datetime, timedelta

app = FastAPI(title="Plataforma Caquetá v8 - Admin Dashboard")

# --- CONFIGURACIÓN DE SERVICIOS ---
SEMANTIC_ENGINE_URL = os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql")
if os.getenv("VERCEL"):
    SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", SEMANTIC_ENGINE_URL)

BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

# --- SEGURIDAD Y JWT ---
SECRET_KEY = "caqueta_secret_key_123"
ALGORITHM = "HS256"

app.add_middleware(SessionMiddleware, secret_key="session_secret_xyz_789", same_site="lax", https_only=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURACIÓN GOOGLE OAUTH ---
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"), 
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"), 
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

users_db = {
    "admin@gmail.com": {"password": "admin", "role": "admin", "name": "Administrador Principal"}
}

chat_context = {} 

async def query_semantic_engine(sparql_query: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=20.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error consultando Motor Semántico: {e}")
            return []

class UserLogin(BaseModel):
    email: str
    password: str

class UserRegister(BaseModel):
    email: str
    password: str
    role: str
    name: str

def create_token(data: dict):
    payload = data.copy()
    payload.update({"exp": datetime.utcnow() + timedelta(hours=24)})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/api/v1/register")
async def register(user: UserRegister):
    users_db[user.email] = {"password": user.password, "role": user.role, "name": user.name}
    return {"status": "ok"}

@app.post("/api/v1/login")
async def login(data: UserLogin):
    u = users_db.get(data.email)
    if u and u["password"] == data.password:
        token = create_token({"email": data.email, "role": u["role"], "name": u["name"]})
        return {"role": u["role"], "name": u["name"], "email": data.email, "token": token}
    raise HTTPException(status_code=401)

@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", request.url_for('google_auth_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            return HTMLResponse(content="<h2>Error: No se recibió información de Google.</h2>", status_code=400)
        
        email = user_info['email']
        if email not in users_db:
            users_db[email] = {
                "password": str(random.randint(100000, 999999)),
                "role": "turista",
                "name": user_info['name']
            }
        
        u = users_db[email]
        jwt_token = create_token({"email": email, "role": u["role"], "name": u["name"]})
        
        target_url = "/?token=" + jwt_token if os.getenv("VERCEL") else f"http://localhost/?token={jwt_token}"
        return HTMLResponse(content=f"""
            <html>
                <body style="background:#064e3b; color:white; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;">
                    <div style="text-align:center;">
                        <h2>¡Sesión Validada!</h2>
                        <p>Entrando a la plataforma...</p>
                        <script>
                            window.location.replace("{target_url}");
                        </script>
                    </div>
                </body>
            </html>
        """)
    except Exception as e:
        print(f"Error en Google Callback: {e}")
        error_url = "/?error=auth_failed" if os.getenv("VERCEL") else "http://localhost/?error=auth_failed"
        return RedirectResponse(url=error_url)

@app.get("/api/v1/actividades")
async def get_actividades(municipio: str = None, categoria: str = None):
    # SPARQL optimizado
    query = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT DISTINCT ?sitio ?tipo_uri ?mun_uri ?clima ?dif
    WHERE {{
      ?sitio <{BASE_PREFIX}ubicadaEn> ?mun_uri .
      ?sitio rdf:type ?tipo_uri .
      FILTER(?tipo_uri != <http://www.w3.org/2002/07/owl#NamedIndividual> && ?tipo_uri != <http://www.w3.org/2002/07/owl#Class>)
      OPTIONAL {{ ?mun_uri <{BASE_PREFIX}clima> ?clima . }}
      OPTIONAL {{ ?sitio <{BASE_PREFIX}nivelDificultad> ?dif . }}
    }}
    """
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    
    for row in results:
        m_uri = row.get("mun_uri", "")
        t_uri = row.get("tipo_uri", "")
        s_uri = row.get("sitio", "")
        
        m_name = m_uri.split("#")[-1].replace("_", " ") if "#" in m_uri else m_uri
        t_name = t_uri.split("#")[-1] if "#" in t_uri else t_uri
        s_name = s_uri.split("#")[-1].replace("_", " ") if "#" in s_uri else s_uri
        
        if municipio and municipio.lower() not in m_name.lower(): continue
        if categoria and categoria.lower() not in t_name.lower(): continue
        
        if s_name not in seen:
            lista.append({
                "id": s_name,
                "categoria": t_name,
                "municipio": m_name,
                "clima": row.get("clima", "Tropical"),
                "dificultad": row.get("dif", "Media")
            })
            seen.add(s_name)
    return lista

# --- IA CON MEMORIA DE CONTEXTO (HUMANIZADA 2.0) ---
@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    
    if user_id not in chat_context: 
        chat_context[user_id] = {"mun": None, "cat": None, "last_results": []}
    
    ctx = chat_context[user_id]
    
    # 1. SALUDOS Y CORTESÍA
    if any(greet in text for greet in ["hola", "buenos dias", "buenas tardes"]):
        return {"reply": "¡Hola! Soy tu guía semántico del Caquetá. ¿A qué municipio te gustaría viajar hoy o qué tipo de actividad buscas?"}

    # 2. DETECCIÓN DE MUNICIPIOS
    muns = ["florencia", "morelia", "doncello", "belen", "san vicente", "puerto rico"]
    for m in muns:
        if m in text: ctx["mun"] = m

    # 3. DETECCIÓN DE CATEGORÍAS (Mapeo a la Ontología)
    cats_map = {
        "Cascada": ["cascada", "chorro", "quebrada", "caida"],
        "Alojamiento": ["hospedaje", "hotel", "dormir", "alojamiento", "donde quedar", "posada"],
        "CaminataEcologica": ["caminata", "senderismo", "senderos", "caminar"],
        "TurismoExtremo": ["extremo", "deporte", "aventura", "rapel"]
    }
    for official, aliases in cats_map.items():
        if any(alias in text for alias in aliases):
            ctx["cat"] = official

    # 4. CASO: DETALLES PROFUNDOS
    if any(word in text for word in ["más información", "detalle", "hablame mas", "cuéntame"]):
        if ctx["last_results"]:
            s = random.choice(ctx["last_results"])
            return {"reply": f"Hablemos de **{s['id']}**. Es un sitio de tipo {s['categoria']} ubicado en {s['municipio']}. Quienes lo visitan disfrutan de un clima {s['clima']} y su acceso tiene una dificultad {s['dificultad']}. ¿Te interesa conocer otro lugar?"}
        return {"reply": "Claro, pero primero dime qué municipio o actividad te interesa para darte detalles reales."}

    # 5. CASO: CLIMA
    if "clima" in text or "temperatura" in text:
        if not ctx["mun"]: return {"reply": "¿De qué municipio quieres conocer el clima?"}
        q = f"SELECT ?clima WHERE {{ ?m <{BASE_PREFIX}clima> ?clima . FILTER(CONTAINS(LCASE(STR(?m)), '{ctx['mun']}')) }} LIMIT 1"
        res = await query_semantic_engine(q)
        clima = res[0]['clima'] if res else "Cálido"
        return {"reply": f"El clima en {ctx['mun'].capitalize()} es predominantemente **{clima}**. ¡Perfecto para la aventura!"}

    # 6. LÓGICA DE BÚSQUEDA Y RESPUESTA
    results = await get_actividades(municipio=ctx["mun"], categoria=ctx["cat"])
    
    # Si no hay resultados con el filtro de categoría, intentamos solo municipio para ser útiles
    if not results and ctx["mun"] and ctx["cat"]:
        results = await get_actividades(municipio=ctx["mun"])
        if results:
            msg = f"No tengo registros exactos de {ctx['cat']} en {ctx['mun'].capitalize()}, pero encontré {len(results)} otros lugares allí. ¿Te gustaría ver cascadas o caminatas?"
            ctx["cat"] = None
            return {"reply": msg}

    if not results:
        return {"reply": "Vaya, no encontré datos para esa búsqueda en mi ontología. ¿Qué tal si probamos con un municipio como Florencia o Morelia?"}

    ctx["last_results"] = results
    
    # Respuesta amigable según el contexto
    if ctx["mun"] and ctx["cat"]:
        return {"reply": f"¡Excelente elección! En {ctx['mun'].capitalize()} encontré {len(results)} opciones de {ctx['cat']}. Te sugiero visitar **{results[0]['id']}**. ¿Quieres que te cuente más sobre este sitio?"}
    
    if ctx["mun"]:
        return {"reply": f"En {ctx['mun'].capitalize()} hay {len(results)} lugares increíbles registrados en mi base de datos. ¿Buscas cascadas, caminatas o quizás un sitio para dormir?"}

    # Fallback final
    rec = random.choice(results)
    return {"reply": f"¡El Caquetá es asombroso! Tengo {len(results)} sitios mapeados. Por ejemplo, en {rec['municipio']} podrías visitar **{rec['id']}**. ¿Qué municipio te gustaría explorar?"}

@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    q1 = f"SELECT ?m (COUNT(DISTINCT ?s) as ?c) WHERE {{ ?s <{BASE_PREFIX}ubicadaEn> ?m }} GROUP BY ?m"
    res1_raw = await query_semantic_engine(q1)
    res1 = {row["m"].split("#")[-1].replace("_", " "): int(row["c"]) for row in res1_raw}
    
    q2 = f"SELECT ?t (COUNT(DISTINCT ?s) as ?c) WHERE {{ ?s a ?t . FILTER(?t != <http://www.w3.org/2002/07/owl#NamedIndividual> && ?t != <http://www.w3.org/2002/07/owl#Class>) }} GROUP BY ?t"
    res2_raw = await query_semantic_engine(q2)
    res2 = {row["t"].split("#")[-1]: int(row["c"]) for row in res2_raw}
    
    async with httpx.AsyncClient() as client:
        try:
            status_resp = await client.get(SEMANTIC_ENGINE_URL.replace("/sparql", "/status"))
            total_tripletas = status_resp.json().get("tripletas", 0)
        except:
            total_tripletas = 0

    return {"municipios": res1, "categorias": res2, "usuarios_activos": len(users_db), "total_tripletas": total_tripletas}

@app.get("/api/v1/admin/users")
async def get_all_users():
    return [{"email": email, "name": u["name"], "role": u["role"]} for email, u in users_db.items()]

@app.get("/api/v1/admin/ontology/full")
async def get_full_ontology():
    query = "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"
    results = await query_semantic_engine(query)
    return [{"sujeto": row["s"].split("#")[-1] if "#" in row["s"] else row["s"], 
             "predicado": row["p"].split("#")[-1] if "#" in row["p"] else row["p"], 
             "objeto": row["o"].split("#")[-1] if "#" in row["o"] else row["o"]} for row in results]

@app.get("/")
async def read_index():
    return {"message": "API Backend Caquetá activa."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
