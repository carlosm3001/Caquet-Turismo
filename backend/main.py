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

app = FastAPI(title="Amazonia-IA V4.0 - Clean Data & Expert Guide")

# Middleware para Vercel
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("VERCEL"): request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ProxyHeadersMiddleware)

SECRET_KEY = os.getenv("JWT_SECRET", "caqueta_safe_2026")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SEMANTIC_ENGINE_URL = os.getenv("PROD_SEMANTIC_ENGINE_URL", os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql"))
BASE_PREFIX = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"

# Cerebro Gemini
llm_model = None
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        llm_model = genai.GenerativeModel('gemini-1.5-flash')
    except: pass

oauth = OAuth()
if os.getenv("GOOGLE_CLIENT_ID"):
    oauth.register(
        name='google', client_id=os.getenv("GOOGLE_CLIENT_ID"), 
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
    
    # LISTA DE NOMBRES A IGNORAR (DATOS DE PRUEBA)
    blacklist = ["bitchip", "wrapsafe", "fintone", "span", "ronstring", "prodder", "alpha", "bravo", "charlie", "delta"]

    for row in results:
        s_name = row.get("sitio", "").split("#")[-1].replace("_", " ")
        m_uri = row.get("mun_uri", "").lower()
        t_uri = row.get("tipo_uri", "").lower()
        
        # FILTRO DE CALIDAD
        if any(bad in s_name.lower() for bad in blacklist): continue
        if municipio and municipio.lower() not in m_uri: continue
        if categoria and categoria.lower() not in t_uri: continue
        
        if s_name not in seen:
            lista.append({
                "id": s_name, "categoria": row.get("tipo_uri", "").split("#")[-1], 
                "municipio": row.get("mun_uri", "").split("#")[-1].replace("_", " "), 
                "clima": row.get("clima", "Cálido Selvático"), "dificultad": row.get("dif", "Media"), 
                "imagen": row.get("img", "")
            })
            seen.add(s_name)
    return lista

# --- IA CON GUÍA EXPERTO (V4.0) ---
@app.post("/api/v1/chat")
async def chat_ai(payload: dict = Body(...)):
    text = payload.get("message", "").lower()
    user_id = payload.get("email", "default")
    if user_id not in chat_context: chat_context[user_id] = {"history": [], "suggested": [], "mun": None, "cat": None, "last_rec": None}
    ctx = chat_context[user_id]
    
    # 1. DETECTAR INTENCIÓN DE DETALLES
    if any(word in text for word in ["detalle", "más información", "cuentame", "como es"]):
        if ctx["last_rec"]:
            s = ctx["last_rec"]
            return {"reply": f"¡Por supuesto! El sitio **{s['id']}** es maravilloso. Es de tipo {s['categoria']} y se encuentra en {s['municipio']}. Quienes lo visitan disfrutan de un clima {s['clima']} y el acceso es de dificultad {s['dificultad']}. ¿Te gustaría saber de otro lugar?"}

    # 2. DETECTAR MUNICIPIO Y CATEGORÍA
    muns = ["florencia", "morelia", "doncello", "belen", "san vicente"]
    cats_map = {"cascada": ["cascada", "chorro", "agua"], "alojamiento": ["hospedaje", "dormir", "estadia", "alojamiento", "hotel"]}
    
    for m in muns: 
        if m in text: ctx["mun"] = m
    for cat_id, aliases in cats_map.items():
        if any(a in text for a in aliases): ctx["cat"] = cat_id

    # 3. OBTENER DATOS LIMPIOS
    sitios = await get_actividades(municipio=ctx["mun"], categoria=ctx["cat"])
    random.shuffle(sitios)
    
    if llm_model:
        try:
            data_context = "\n".join([f"- {s['id']} ({s['categoria']}) en {s['municipio']}" for s in sitios[:10]])
            prompt = f"Eres Amazonia-IA, un guía experto del Caquetá. Datos reales:\n{data_context}\nUsuario dice: {text}\nResponde humano, breve y sugiere un sitio de la lista."
            response = llm_model.generate_content(prompt)
            return {"reply": response.text}
        except: pass

    # 4. FALLBACK INTELIGENTE (MODO EXPERTO SIN REPETICIONES)
    if sitios:
        rec = sitios[0]
        ctx["last_rec"] = rec # Guardamos para los detalles
        if ctx["mun"] and ctx["cat"]:
            return {"reply": f"¡Excelente elección! En {ctx['mun'].capitalize()} tengo {len(sitios)} opciones de {ctx['cat']}. Te sugiero visitar **{rec['id']}**. ¿Te gustaría que te cuente los detalles técnicos?"}
        if ctx["mun"]:
            return {"reply": f"He encontrado {len(sitios)} destinos en {ctx['mun'].capitalize()}. ¿Buscas una cascada o un sitio para pasar la noche?"}
        
    return {"reply": "¡Hola! Soy tu guía del Caquetá. ¿Qué municipio te gustaría explorar hoy?"}

@app.get("/api/v1/auth/google/callback")
async def google_auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        jwt_token = jwt.encode({"email": user_info['email'], "name": user_info['name'], "role": "turista", "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm="HS256")
        return HTMLResponse(content=f"<html><script>window.location.replace('/?token={jwt_token}');</script></html>")
    except: return RedirectResponse(url="/")

@app.get("/")
async def root(): return {"status": "V4.0 Clean Engine Ready"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
