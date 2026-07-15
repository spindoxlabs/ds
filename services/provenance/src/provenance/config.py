from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROVENANCE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@172.17.0.1:35432/provenance"
    debug: bool = False
    base_url: str = "https://provenance.dataspaces.localhost"
    context_url: str = "https://provenance.dataspaces.localhost/prov/context"
    max_lineage_depth: int = 20


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
