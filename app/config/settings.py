from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    GROQ = "groq"
    AZURE = "azure"


class Settings(BaseSettings):

    # Application
    app_name: str = "MyImpact AI"
    app_version: str = "0.1.0"
    app_env: str = "development"

    ai_service_host: str = "127.0.0.1"
    ai_service_port: int = 8000
    
    # Application-DB
    database_url: str 

    # LLM
    llm_provider: str = "groq"

    # Groq
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = ""
    azure_openai_deployment: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
@lru_cache
def get_settings() -> Settings:
    return Settings()