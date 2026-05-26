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

app = FastAPI(title="Amazonia-IA V5.5")


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
    fecha_fin: str
    personas: int
    dias: int
    user_email: str
    user_name: str
    total_pago: int


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


@app.post("/api/v1/actividades")
async def post_actividad(act: ActivityCreate):
    safe_id = act.id.replace(" ", "_")
    safe_mun = act.municipio.replace(" ", "_")
    query = f"""
    PREFIX : <{BASE_PREFIX}> 
    INSERT DATA {{ 
        :{safe_id} rdf:type :Actividad ; 
            :nombreActividad '{act.nombre}' ; 
            :tipoActividad '{act.categoria}' ; 
            :ubicadaEn :{safe_mun} ; 
            :precio {act.precio} ; 
            :disponibilidad 'Disponible' ;
            :imagenURL '{act.imagen}' . 
    }}
    """
    await query_semantic_engine(query)
    return {"status": "success"}


@app.put("/api/v1/actividades/{act_id}")
async def update_actividad(act_id: str, act: ActivityCreate):
    safe_mun = act.municipio.replace(" ", "_")
    # Para simplificar el update en SPARQL, borramos las propiedades existentes y las re-insertamos
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    DELETE {{ :{act_id} ?p ?o }}
    WHERE {{ :{act_id} ?p ?o }} ;
    INSERT DATA {{
        :{act_id} rdf:type :Actividad ;
            :nombreActividad '{act.nombre}' ;
            :tipoActividad '{act.categoria}' ;
            :ubicadaEn :{safe_mun} ;
            :precio {act.precio} ;
            :imagenURL '{act.imagen}' .
    }}
    """
    await query_semantic_engine(query)
    return {"status": "success"}


@app.patch("/api/v1/actividades/{act_id}/status")
async def toggle_status(act_id: str, payload: dict = Body(...)):
    new_status = payload.get("status", "Disponible")
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    DELETE {{ :{act_id} :disponibilidad ?o }}
    WHERE {{ :{act_id} :disponibilidad ?o }} ;
    INSERT DATA {{ :{act_id} :disponibilidad '{new_status}' }}
    """
    await query_semantic_engine(query)
    return {"status": "success"}


@app.patch("/api/v1/actividades/{act_id}/visibility")
async def toggle_visibility(act_id: str, payload: dict = Body(...)):
    new_status = payload.get("status", "Disponible")
    query = f"""
    PREFIX : <{BASE_PREFIX}>
    DELETE {{ :{act_id} :disponibilidad ?old_status }}
    WHERE {{ OPTIONAL {{ :{act_id} :disponibilidad ?old_status }} }} ;
    INSERT DATA {{ :{act_id} :disponibilidad '{new_status}' }}
    """
    try:
        result = await query_semantic_engine(query)
        print(f"DEBUG VISIBILITY - act_id: {act_id}, status: {new_status}")
        return {"status": "success", "new_status": new_status, "result": result}
    except Exception as e:
        print(f"ERROR VISIBILITY: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/users")
async def get_admin_users():
    await sync_users_from_ontology()
    return [
        {"email": e, "name": i["name"], "role": i["role"]} for e, i in users_db.items()
    ]


@app.get("/api/v1/admin/full-stats")
async def get_admin_full_stats():
    q_res = f"PREFIX : <{BASE_PREFIX}> SELECT ?reserva ?user ?fecha ?personas ?dias ?precio_base WHERE {{ ?reserva rdf:type :Reserva . ?reserva :usuarioReserva ?user . ?reserva :fechaInicio ?fecha . ?reserva :cantidadPersonas ?personas . ?reserva :cantidadDias ?dias . ?reserva :lugarReservado ?lugar_uri . OPTIONAL {{ ?lugar_uri :precio ?precio_base }} }}"
    res_data = await query_semantic_engine(q_res)
    total_ingresos = sum(
        int(r.get("precio_base", 0)) * int(r.get("dias", 1)) for r in res_data
    )
    q_tipo = f"PREFIX : <{BASE_PREFIX}> SELECT ?tipo (COUNT(?s) as ?c) WHERE {{ ?s rdf:type :Actividad . ?s :tipoActividad ?tipo }} GROUP BY ?tipo"
    tipos = await query_semantic_engine(q_tipo)
    return {
        "kpis": {
            "total_reservas": len(res_data),
            "ingresos_proyectados": total_ingresos,
            "usuarios_activos": len(users_db),
            "puntos_interes": 0,
        },
        "distribucion_actividad": {row["tipo"]: int(row["c"]) for row in tipos},
        "ultimas_reservas": [
            {"id": r["reserva"].split("#")[-1], "user": r["user"], "fecha": r["fecha"]}
            for r in res_data[-5:]
        ],
    }


@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    if not GEMINI_KEY:
        return {"reply": "¡Hola! Configura mi API Key para guiarte."}
    
    message = payload.get("message", "")
    
    # 1. Extracción de CONOCIMIENTO TOTAL de la Ontología
    query_context = f"""
    PREFIX : <{BASE_PREFIX}> 
    SELECT DISTINCT ?nombre ?mun_uri ?precio ?dif ?tipo ?desc WHERE {{ 
        ?s rdf:type :Actividad . 
        ?s :nombreActividad ?nombre . 
        ?s :ubicadaEn ?mun_uri . 
        OPTIONAL {{ ?s :precio ?precio }} 
        OPTIONAL {{ ?s :nivelDificultad ?dif }} 
        OPTIONAL {{ ?s :tipoActividad ?tipo }} 
        OPTIONAL {{ ?s :descripcion ?desc }}
    }}
    """
    raw_data = await query_semantic_engine(query_context)
    
    # 2. Formateo de Base de Conocimiento para la IA
    knowledge_base = []
    for item in raw_data:
        mun = item.get("mun_uri", "").split("#")[-1].replace("_", " ")
        info = f"- {item.get('nombre')} en {mun}: Tipo {item.get('tipo', 'N/A')}, Dificultad {item.get('dif', 'N/A')}, Precio ${item.get('precio', 0)}. Descripción: {item.get('desc', 'Sin descripción')}"
        knowledge_base.append(info)
    
    context_str = "\\n".join(knowledge_base)

    # 3. Prompt de Misión Crítica (Basado estrictamente en datos)
    prompt = f"""
    Eres BioBot, el cerebro de IA de la plataforma 'Caquetá Bio'. 🌿🧠
    Tu conocimiento proviene EXCLUSIVAMENTE de una base de datos semántica (Ontología RDF).
    
    BASE DE DATOS REAL (Lo único que existe):
    {context_str}
    
    REGLAS DE ORO:
    1. Si el viajero pregunta por un destino que NO está en la lista anterior, responde amablemente que por ahora no lo tenemos en el catálogo semántico.
    2. Usa los PRECIOS y DETALLES exactos que aparecen en la lista.
    3. Si preguntan por recomendaciones (ej: "algo barato" o "de aventura"), busca en la lista anterior los que coincidan con precio bajo o tipo aventura.
    4. Responde con calidez amazónica, pero con precisión técnica. Usa emojis (🌴, 💦, 🦜).
    5. No menciones que eres una IA ni que tienes una "lista". Eres un guía experto.
    
    PREGUNTA DEL VIAJERO:
    {message}
    """

    try:
        # 4. Selección Inteligente de Modelo (Anti-404)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Estrategia de selección: Flash > Pro > El primero que funcione
        selected_model = None
        for target in ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-pro"]:
            if target in available_models:
                selected_model = target
                break
        
        if not selected_model and available_models:
            selected_model = available_models[0]
        
        if not selected_model:
            return {"reply": "BioBot no encuentra modelos de IA disponibles para esta API Key. 🦜"}

        model = genai.GenerativeModel(model_name=selected_model)
        response = model.generate_content(prompt)
        
        if response and response.text:
            return {"reply": response.text}
        return {"reply": "BioBot está analizando las tripletas semánticas... 🦜 Intenta preguntarme de nuevo."}
        
    except Exception as e:
        print(f"CHAT ERROR: {str(e)}")
        return {"reply": f"BioBot está sincronizando el conocimiento... (Error de modelo: {str(e)[:80]}). ¡El Caquetá te espera! 🌴"}


@app.post("/api/v1/reservas")
async def post_reserva(res: ReservaRequest):
    res_id = f"Reserva_{int(datetime.utcnow().timestamp())}"
    query = f"""
    PREFIX : <{BASE_PREFIX}> 
    INSERT DATA {{ 
        :{res_id} rdf:type :Reserva ; 
            :fechaInicio '{res.fecha_inicio}' ; 
            :fechaFin '{res.fecha_fin}' ; 
            :cantidadPersonas {res.personas} ; 
            :cantidadDias {res.dias} ; 
            :totalPago {res.total_pago} ;
            :usuarioReserva '{res.user_email}' ; 
            :lugarReservado :{res.lugar_id} . 
    }}
    """
    await query_semantic_engine(query)
    return {"status": "success", "id": res_id}


@app.get("/api/v1/mis-reservas")
async def get_mis_reservas(email: str):
    query = f"""
    PREFIX : <{BASE_PREFIX}> 
    SELECT ?reserva ?f_ini ?f_fin ?personas ?dias ?nombre_lugar ?total WHERE {{ 
        ?reserva rdf:type :Reserva . 
        ?reserva :usuarioReserva '{email}' . 
        ?reserva :fechaInicio ?f_ini . 
        ?reserva :fechaFin ?f_fin . 
        ?reserva :cantidadPersonas ?personas . 
        ?reserva :cantidadDias ?dias . 
        ?reserva :totalPago ?total .
        ?reserva :lugarReservado ?lugar_uri . 
        ?lugar_uri :nombreActividad ?nombre_lugar . 
    }}
    """
    results = await query_semantic_engine(query)
    return [
        {
            "id": r["reserva"].split("#")[-1],
            "fecha": f"{r['f_ini']} al {r['f_fin']}",
            "personas": r["personas"],
            "dias": r["dias"],
            "lugar": r["nombre_lugar"],
            "precio_total": int(r["total"]),
        }
        for r in results
    ]


@app.delete("/api/v1/reservas/{reserva_id}")
async def delete_reserva(reserva_id: str):
    await query_semantic_engine(
        f"PREFIX : <{BASE_PREFIX}> DELETE WHERE {{ :{reserva_id} ?p ?o }}"
    )
    return {"status": "success"}


@app.get("/api/v1/stats")
async def get_stats():
    # 1. Total Atractivos
    q_total = f"PREFIX : <{BASE_PREFIX}> SELECT (COUNT(?s) as ?total) WHERE {{ ?s rdf:type :Actividad }}"
    total_res = await query_semantic_engine(q_total)
    total = int(total_res[0]["total"]) if total_res else 0

    # 2. Por Municipio
    q_mun = f"PREFIX : <{BASE_PREFIX}> SELECT ?mun_uri (COUNT(?s) as ?count) WHERE {{ ?s rdf:type :Actividad . ?s :ubicadaEn ?mun_uri }} GROUP BY ?mun_uri"
    mun_res = await query_semantic_engine(q_mun)
    por_municipio = {
        row["mun_uri"].split("#")[-1].replace("_", " "): int(row["count"])
        for row in mun_res
    }

    # 3. Por Dificultad
    q_dif = f"PREFIX : <{BASE_PREFIX}> SELECT ?dif (COUNT(?s) as ?count) WHERE {{ ?s rdf:type :Actividad . ?s :nivelDificultad ?dif }} GROUP BY ?dif"
    dif_res = await query_semantic_engine(q_dif)
    por_dificultad = {row["dif"]: int(row["count"]) for row in dif_res}

    return {
        "total_atractivos": total,
        "por_municipio": por_municipio,
        "por_dificultad": por_dificultad,
        "grafo_status": "Sincronizado",
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
