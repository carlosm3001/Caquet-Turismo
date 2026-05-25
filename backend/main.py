from fastapi import FastAPI, Body, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
import os
import random
import jwt
import httpx
import google.generativeai as genai
from datetime import datetime, timedelta

try:
    from config import settings
except ImportError:
    try:
        from .config import settings
    except ImportError:
        # Fallback manual si falla la importación del módulo config
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

print(f"Iniciando Backend en Vercel: {settings.VERCEL}")

app = FastAPI(title="Amazonia-IA V4.5 - Enhanced Semantic Data")


# --- MIDDLEWARES ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"Request: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        print(f"Error procesando request: {str(e)}")
        return HTMLResponse(content=f"Internal Server Error: {str(e)}", status_code=500)


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

# --- CONFIGURACIÓN DE SERVICIOS ---
SEMANTIC_ENGINE_URL = settings.SEMANTIC_ENGINE_URL
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

# --- IA GEMINI ---
llm_model = None
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        llm_model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        print(f"IA Error: {e}")

# --- CONFIGURACIÓN GOOGLE OAUTH ---
oauth = OAuth()
if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


# --- MODELOS DE DATOS ---
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


# --- PERSISTENCIA SEMÁNTICA DE USUARIOS ---
users_db = {
    "admin@gmail.com": {
        "password": "admin",
        "role": "admin",
        "name": "Administrador Principal",
    }
}
_users_synced = False


async def query_semantic_engine(sparql_query: str):
    async with httpx.AsyncClient() as client:
        try:
            print(f"Consultando Motor Semántico en: {SEMANTIC_ENGINE_URL}")
            response = await client.post(
                SEMANTIC_ENGINE_URL, json={"query": sparql_query}, timeout=30.0
            )
            if response.status_code != 200:
                print(
                    f"Error del Motor Semántico: {response.status_code} - {response.text}"
                )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(
                f"Error de conexión con Motor Semántico ({SEMANTIC_ENGINE_URL}): {str(e)}"
            )
            return []


async def sync_users_from_ontology():
    global _users_synced
    if _users_synced:
        return
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    SELECT ?email ?name ?role ?pass
    WHERE {{
      ?u rdf:type :Usuario .
      ?u :userEmail ?email .
      ?u :userName ?name .
      ?u :userRole ?role .
      OPTIONAL {{ ?u :userPassword ?pass }}
    }}
    """
    results = await query_semantic_engine(query)
    for row in results:
        email = str(row["email"])
        p_val = str(row.get("pass")) if row.get("pass") else None

        if email not in users_db or (p_val and p_val != "None"):
            users_db[email] = {
                "name": str(row["name"]),
                "role": str(row["role"]),
                "password": p_val if (p_val and p_val != "None") else "google_auth",
            }
    _users_synced = True


def create_token(data: dict):
    payload = data.copy()
    payload.update({"exp": datetime.utcnow() + timedelta(hours=24)})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/api/v1/register")
async def register(data: RegisterRequest):
    safe_email = data.email.replace("@", "_at_").replace(".", "_")
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    INSERT DATA {{
      :User_{safe_email} rdf:type :Usuario ;
                         :userEmail "{data.email}" ;
                         :userName "{data.name}" ;
                         :userRole "turista" ;
                         :userPassword "{data.password}" .
    }}
    """
    await query_semantic_engine(query)
    users_db[data.email] = {
        "password": data.password,
        "role": "turista",
        "name": data.name,
    }
    token = create_token({"email": data.email, "name": data.name, "role": "turista"})
    return {"token": token}


@app.post("/api/v1/login")
async def login(data: LoginRequest):
    await sync_users_from_ontology()
    u = users_db.get(data.email)
    if u and u["password"] == data.password:
        token = create_token(
            {"email": data.email, "role": u["role"], "name": u["name"]}
        )
        return {"token": token, "role": u["role"], "name": u["name"]}
    raise HTTPException(status_code=401, detail="Credenciales incorrectas")


@app.get("/api/v1/auth/google")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=501, detail="Google OAuth no está configurado en el servidor"
        )
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        return RedirectResponse(url="/?error=oauth_not_configured")
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")
        if not user_info:
            raise HTTPException(status_code=400)

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
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT DISTINCT ?sitio ?nombre ?tipo_uri ?mun_uri ?clima ?dif ?tipo_act ?precio ?disp ?desc ?horario ?img
    WHERE {{
      ?sitio rdf:type :Actividad .
      ?sitio :ubicadaEn ?mun_uri .
      OPTIONAL {{ ?sitio :nombreActividad ?nombre . }}
      OPTIONAL {{ ?mun_uri :clima ?clima . }}
      OPTIONAL {{ ?sitio :nivelDificultad ?dif . }}
      OPTIONAL {{ ?sitio :tipoActividad ?tipo_act . }}
      OPTIONAL {{ ?sitio :precio ?precio . }}
      OPTIONAL {{ ?sitio :disponibilidad ?disp . }}
      OPTIONAL {{ ?sitio :descripcion ?desc . }}
      OPTIONAL {{ ?sitio :horario ?horario . }}
      OPTIONAL {{ ?sitio :imagenURL ?img . }}
      BIND(STR(?nombre) AS ?nameStr)
      FILTER(?nameStr != "None" && ?nameStr != "")
    }}
    """
    results = await query_semantic_engine(query)
    lista = []
    seen = set()
    for row in results:
        s_uri = row.get("sitio", "")
        s_id = s_uri.split("#")[-1]
        if s_id in seen:
            continue

        m_name = row.get("mun_uri", "").split("#")[-1].replace("_", " ")
        t_act = row.get("tipo_act", "General")
        dif = row.get("dif", "Media")

        # Filtros Dinámicos
        if municipio and municipio.lower() not in m_name.lower():
            continue
        if dificultad and dificultad.lower() != dif.lower():
            continue
        if categoria and categoria.lower() not in t_act.lower():
            continue

        lista.append(
            {
                "id": row.get("nombre"),
                "real_id": s_id,
                "categoria": t_act,
                "municipio": m_name,
                "clima": row.get("clima") or "Tropical",
                "dificultad": dif,
                "precio": int(row.get("precio", 0)),
                "disponibilidad": row.get("disp") or "Disponible",
                "descripcion": row.get("desc"),
                "horario": row.get("horario"),
                "imagen": row.get("img"),
            }
        )
        seen.add(s_id)
    return lista


@app.post("/api/v1/actividades")
async def post_actividad(act: ActivityCreate):
    # Sanitizar ID para SPARQL (reemplazar espacios por guiones bajos)
    safe_id = act.id.replace(" ", "_")
    safe_mun = act.municipio.replace(" ", "_")

    query = f"""
    PREFIX : <{BASE_PREFIX}>
    INSERT DATA {{
      :{safe_id} rdf:type :Actividad ;
                :nombreActividad "{act.nombre}" ;
                :tipoActividad "{act.categoria}" ;
                :ubicadaEn :{safe_mun} ;
                :precio {act.precio} ;
                :imagenURL "{act.imagen}" ;
                :nivelDificultad "Media" ;
                :disponibilidad "Disponible" ;
                :descripcion "Nuevo destino explorado en el Caquetá." ;
                :horario "8:00 AM - 5:00 PM" .
    }}
    """
    await query_semantic_engine(query)
    return {"status": "success", "id": safe_id}


@app.get("/api/v1/admin/users")
async def get_admin_users():
    await sync_users_from_ontology()
    return [
        {"email": email, "name": info["name"], "role": info["role"]}
        for email, info in users_db.items()
    ]


@app.get("/api/v1/admin/user-activities/{email}")
async def get_user_activities(email: str):
    # Reutilizamos la lógica de mis-reservas para el administrador
    return await get_mis_reservas(email)


@app.get("/api/v1/stats")
async def get_semantic_stats():
    # 1. Total de atractivos
    q1 = f"PREFIX : <{BASE_PREFIX}> SELECT (COUNT(?s) as ?count) WHERE {{ ?s rdf:type :Actividad }}"
    # 2. Atractivos por Municipio
    q2 = f"PREFIX : <{BASE_PREFIX}> SELECT ?mun (COUNT(?s) as ?count) WHERE {{ ?s :ubicadaEn ?m . BIND(STRAFTER(STR(?m), '#') as ?mun) }} GROUP BY ?mun"
    # 3. Distribución por Dificultad
    q3 = f"PREFIX : <{BASE_PREFIX}> SELECT ?dif (COUNT(?s) as ?count) WHERE {{ ?s :nivelDificultad ?dif }} GROUP BY ?dif"

    r1 = await query_semantic_engine(q1)
    r2 = await query_semantic_engine(q2)
    r3 = await query_semantic_engine(q3)

    return {
        "total_atractivos": int(r1[0]["count"]) if r1 else 0,
        "por_municipio": {
            row["mun"].replace("_", " "): int(row["count"]) for row in r2
        },
        "por_dificultad": {row["dif"]: int(row["count"]) for row in r3},
        "grafo_status": "Vívido - Web Semántica 1.1",
    }


@app.get("/api/v1/admin/full-stats")
async def get_admin_full_stats():
    # 1. Todas las reservas con detalles de lugar y precio para métricas financieras
    q_reservas = f"""
    PREFIX : <{BASE_PREFIX}>
    SELECT ?reserva ?user ?fecha ?personas ?dias ?precio_base
    WHERE {{
      ?reserva rdf:type :Reserva .
      ?reserva :usuarioReserva ?user .
      ?reserva :fechaInicio ?fecha .
      ?reserva :cantidadPersonas ?personas .
      ?reserva :cantidadDias ?dias .
      ?reserva :lugarReservado ?lugar_uri .
      OPTIONAL {{ ?lugar_uri :precio ?precio_base }}
    }}
    """
    res_data = await query_semantic_engine(q_reservas)

    total_ingresos = 0
    for r in res_data:
        p_base = int(r.get("precio_base", 0))
        dias = int(r.get("dias", 1))
        total_ingresos += p_base * dias

    # 2. Conteo de Actividades por tipo
    q_tipos = f"PREFIX : <{BASE_PREFIX}> SELECT ?tipo (COUNT(?s) as ?count) WHERE {{ ?s rdf:type :Actividad . ?s :tipoActividad ?tipo }} GROUP BY ?tipo"
    tipos_data = await query_semantic_engine(q_tipos)

    return {
        "kpis": {
            "total_reservas": len(res_data),
            "ingresos_proyectados": total_ingresos,
            "usuarios_activos": len(users_db),
            "puntos_interes": int(
                (
                    await query_semantic_engine(
                        f"PREFIX : <{BASE_PREFIX}> SELECT (COUNT(?s) as ?c) WHERE {{ ?s rdf:type :Actividad }}"
                    )
                )[0]["c"]
            ),
        },
        "distribucion_actividad": {
            row["tipo"]: int(row["count"]) for row in tipos_data
        },
        "ultimas_reservas": [
            {"id": r["reserva"].split("#")[-1], "user": r["user"], "fecha": r["fecha"]}
            for r in res_data[-5:]  # Últimas 5
        ],
    }


@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    # Lógica de IA mejorada
    # Aquí podrías integrar el llm_model si lo tienes configurado
    return {
        "reply": "Estoy procesando tu solicitud sobre el Caquetá. Por ahora, te recomiendo explorar la sección de destinos."
    }


@app.get("/api/v1/admin/dashboard")
async def admin_dashboard():
    query = "SELECT (COUNT(*) as ?count) WHERE { ?s ?p ?o }"
    results = await query_semantic_engine(query)
    total_rdf = results[0].get("count", "0") if results else "0"
    return {
        "total_tripletas": total_rdf,
        "total_usuarios": len(users_db),
        "status_motor": "online",
    }


@app.get("/api/v1/status")
async def get_status():
    return {"status": "online", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/v1/reservas")
async def post_reserva(res: ReservaRequest):
    res_id = f"Reserva_{int(datetime.utcnow().timestamp())}"
    # Usamos la URI del lugar directamente para el vínculo semántico
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    INSERT DATA {{
      :{res_id} rdf:type :Reserva ;
                :fechaInicio "{res.fecha_inicio}" ;
                :cantidadPersonas {res.personas} ;
                :cantidadDias {res.dias} ;
                :usuarioReserva "{res.user_email}" ;
                :lugarReservado :{res.lugar_id} .
    }}
    """
    await query_semantic_engine(query)
    return {"status": "success", "id": res_id}


@app.get("/api/v1/mis-reservas")
async def get_mis_reservas(email: str):
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?reserva ?fecha ?personas ?dias ?lugar_uri ?nombre_lugar ?precio_base
    WHERE {{
      ?reserva rdf:type :Reserva .
      ?reserva :usuarioReserva "{email}" .
      ?reserva :fechaInicio ?fecha .
      ?reserva :cantidadPersonas ?personas .
      ?reserva :cantidadDias ?dias .
      ?reserva :lugarReservado ?lugar_uri .
      ?lugar_uri :nombreActividad ?nombre_lugar .
      ?lugar_uri :precio ?precio_base .
    }}
    """
    results = await query_semantic_engine(query)
    lista = []
    for row in results:
        precio_base = int(row.get("precio_base", 0))
        dias = int(row.get("dias", 1))
        total = precio_base * dias

        lista.append(
            {
                "id": row.get("reserva", "").split("#")[-1],
                "fecha": row.get("fecha"),
                "personas": row.get("personas"),
                "dias": dias,
                "lugar": row.get("nombre_lugar"),
                "precio_total": total,
            }
        )
    return lista


@app.delete("/api/v1/reservas/{reserva_id}")
async def delete_reserva(reserva_id: str):
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    DELETE WHERE {{ :{reserva_id} ?p ?o }}
    """
    await query_semantic_engine(query)
    return {"status": "success", "message": "Reserva cancelada"}


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
