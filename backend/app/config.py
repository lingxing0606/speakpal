import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./speakpal.db")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    admin_key: str = os.getenv("ADMIN_KEY", "admin123")


settings = Settings()
