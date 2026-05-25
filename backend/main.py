import os
import random
import jwt
import httpx
import google.generativeai as genai
from datetime import datetime, timedelta
from fastapi import FastAPI, Body, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware

try:
    from config import settings
except ImportError:
    try:
        from .config import settings
    except ImportError:

        class FallbackSettings:
            JWT_SECRET = os.getenv("JWT_SECRET", "caqueta_safe_2026")
            VERCEL = bool(os.getenv("VERCEL"))
            GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
            GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
            GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
            SEMANTIC_ENGINE_URL = os.getenv(
                "PROD_SEMANTIC_ENGINE_URL",
                os.getenv("SEMANTIC_ENGINE_URL", "http://localhost:3030/sparql"),
            )

        settings = FallbackSettings()

app = FastAPI(title="Amazonia-IA V5.2")


@app.middleware("http")
async def safe_handler(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)


SECRET_KEY = settings.JWT_SECRET
ALGORITHM = "HS256"
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=settings.VERCEL,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

SEMANTIC_ENGINE_URL = settings.SEMANTIC_ENGINE_URL
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

oauth = OAuth()
if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


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


class ActivityCreate(BaseModel):
    id: str
    nombre: str
    categoria: str
    municipio: str
    precio: int
    imagen: str


users_db = {
    "admin@gmail.com": {"password": "admin", "role": "admin", "name": "Administrador"}
}
_users_synced = False


async def query_semantic_engine(sparql_query: str):
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=30.0
            )
            return res.json() if res.status_code == 200 else []
        except Exception:
            return []


async def sync_users_from_ontology():
    global _users_synced
    if _users_synced:
        return
    query = f"PREFIX : <{BASE_PREFIX}> SELECT ?email ?name ?role ?pass WHERE {{ ?u rdf:type :Usuario . ?u :userEmail ?email . ?u :userName ?name . ?u :userRole ?role . OPTIONAL {{ ?u :userPassword ?pass }} }}"
    results = await query_semantic_engine(query)
    for row in results:
        email = str(row["email"])
        users_db[email] = {
            "name": str(row["name"]),
            "role": str(row["role"]),
            "password": str(row.get("pass", "google_auth")),
        }
    _users_synced = True


def create_token(data: dict):
    payload = data.copy()
    payload.update({"exp": datetime.utcnow() + timedelta(hours=24)})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/api/v1/register")
async def register(data: RegisterRequest):
    safe_email = data.email.replace("@", "_at_").replace(".", "_")
    query = f"PREFIX : <{BASE_PREFIX}> INSERT DATA {{ :User_{safe_email} rdf:type :Usuario ; :userEmail '{data.email}' ; :userName '{data.name}' ; :userRole 'turista' ; :userPassword '{data.password}' . }}"
    await query_semantic_engine(query)
    users_db[data.email] = {
        "password": data.password,
        "role": "turista",
        "name": data.name,
    }
    return {
        "token": create_token(
            {"email": data.email, "name": data.name, "role": "turista"}
        )
    }


@app.post("/api/v1/login")
async def login(data: LoginRequest):
    await sync_users_from_ontology()
    u = users_db.get(data.email)
    if u and u["password"] == data.password:
        return {
            "token": create_token(
                {"email": data.email, "role": u["role"], "name": u["name"]}
            ),
            "role": u["role"],
            "name": u["name"],
        }
    raise HTTPException(status_code=401, detail="Credenciales incorrectas")


@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501)
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")
        email = user_info["email"]
        if email not in users_db:
            users_db[email] = {
                "password": str(random.randint(1000, 9999)),
                "role": "turista",
                "name": user_info["name"],
            }
        u = users_db[email]
        jwt_token = create_token({"email": email, "role": u["role"], "name": u["name"]})
        target_url = (
            "/?token=" + jwt_token
            if settings.VERCEL
            else f"http://localhost/?token={jwt_token}"
        )
        return HTMLResponse(
            content=f"<script>window.location.replace('{target_url}');</script>"
        )
    except Exception:
        return RedirectResponse(url="/?error=auth_failed")


@app.get("/api/v1/actividades")
async def get_actividades(
    municipio: str = None, categoria: str = None, dificultad: str = None
):
    query = f"PREFIX : <{BASE_PREFIX}> SELECT DISTINCT ?sitio ?nombre ?mun_uri ?clima ?dif ?tipo_act ?precio ?disp ?desc ?horario ?img WHERE {{ ?sitio rdf:type :Actividad . ?sitio :ubicadaEn ?mun_uri . OPTIONAL {{ ?sitio :nombreActividad ?nombre . }} OPTIONAL {{ ?mun_uri :clima ?clima . }} OPTIONAL {{ ?sitio :nivelDificultad ?dif . }} OPTIONAL {{ ?sitio :tipoActividad ?tipo_act . }} OPTIONAL {{ ?sitio :precio ?precio . }} OPTIONAL {{ ?sitio :disponibilidad ?disp . }} OPTIONAL {{ ?sitio :descripcion ?desc . }} OPTIONAL {{ ?sitio :horario ?horario . }} OPTIONAL {{ ?sitio :imagenURL ?img . }} FILTER(STR(?nombre) != '') }}"
    results = await query_semantic_engine(query)
    lista = []
    for row in results:
        lista.append(
            {
                "id": row.get("nombre"),
                "real_id": row.get("sitio", "").split("#")[-1],
                "categoria": row.get("tipo_act", "General"),
                "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "),
                "clima": row.get("clima") or "Tropical",
                "dificultad": row.get("dif") or "Media",
                "precio": int(row.get("precio", 0)),
                "disponibilidad": row.get("disp") or "Disponible",
                "descripcion": row.get("desc"),
                "horario": row.get("horario"),
                "imagen": row.get("img"),
            }
        )
    return lista


@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    if not GEMINI_KEY:
        return {
            "reply": "¡Hola! Soy BioBot. Configura mi cerebro con una API Key para que pueda ayudarte mejor."
        }
    message = payload.get("message", "")
    query_context = f"PREFIX : <{BASE_PREFIX}> SELECT DISTINCT ?nombre ?mun WHERE {{ ?s rdf:type :Actividad . ?s :nombreActividad ?nombre . ?s :ubicadaEn ?m . ?m :nombreMunicipio ?mun }} LIMIT 10"
    raw_data = await query_semantic_engine(query_context)
    context_str = "Destinos Reales: " + ", ".join(
        [f"{item.get('nombre')} en {item.get('mun')}" for item in raw_data]
    )
    prompt = f"Eres BioBot, guía local del Caquetá. Sé cálido y humano. Contexto: {context_str}. Viajero pregunta: {message}"

    last_err = ""
    # Ciclo de modelos: Intentar desde el más nuevo al más estable
    for m_name in ["gemini-1.5-flash", "gemini-1.0-pro", "gemini-pro"]:
        try:
            model = genai.GenerativeModel(m_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return {"reply": response.text}
        except Exception as e:
            last_err = str(e)
            continue

    return {
        "reply": f"¡Hola! BioBot tiene un problema técnico: {last_err[:100]}. Pero el Caquetá te espera con sus cascadas vivas. ¡Explora la web! 🌴"
    }


@app.get("/api/v1/stats")
async def get_stats():
    return {
        "total_atractivos": 0,
        "por_municipio": {},
        "por_dificultad": {},
        "grafo_status": "Vívido",
    }


@app.get("/api/v1/status")
async def get_status():
    return {"status": "online"}


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html"
    )
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>API Online</h1>"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
