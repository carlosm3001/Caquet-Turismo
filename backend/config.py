try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings
from pydantic import Field
import os

class Settings(BaseSettings):
    # Core settings
    JWT_SECRET: str = Field(default=os.getenv("JWT_SECRET", "caqueta_safe_2026"))
    ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    # OAuth settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8001/api/v1/auth/google/callback")
    # Semantic engine
    SEMANTIC_ENGINE_URL: str = os.getenv(
        "PROD_SEMANTIC_ENGINE_URL",
        os.getenv("SEMANTIC_ENGINE_URL", "http://semantic-engine:3030/sparql"),
    )
    BASE_PREFIX: str = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"
    # Misc
    VERCEL: bool = bool(os.getenv("VERCEL"))

settings = Settings()
