"""환경설정 (pydantic-settings). 모든 시크릿/경로는 .env 에서 주입."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: str = "solar"  # solar(기본) | claude | mock
    anthropic_api_key: str = ""
    solar_api_key: str = ""
    fred_api_key: str = ""
    ecos_api_key: str = ""
    fmp_api_key: str = ""
    rag_corpus_dir: str = "./rag_corpus"
    chroma_dir: str = "./.chroma"
    sqlite_path: str = "./macrolens.db"
    w_causal: float = 0.5
    w_historical: float = 0.5


settings = Settings()
