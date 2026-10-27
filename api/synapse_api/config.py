from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYNAPSE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://synapse:synapse@localhost:5432/synapse"

    # Keycloak (OIDC). Le jeton porte les rôles du royaume dans realm_access.roles.
    oidc_issuer: str = "http://localhost:8080/realms/synapse"
    oidc_audience: str = "synapse-api"

    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def oidc_jwks_url(self) -> str:
        return f"{self.oidc_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
