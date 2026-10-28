from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYNAPSE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://synapse:synapse@localhost:5432/synapse"

    # Keycloak (OIDC). Le jeton porte les rôles du royaume dans realm_access.roles.
    oidc_issuer: str = "http://localhost:8080/realms/synapse"
    oidc_audience: str = "synapse-api"

    cors_origins: list[str] = ["http://localhost:3200"]

    # Passerelle LiteLLM (infra/litellm). Sa clé est lue par l'orchestrateur, jamais montrée aux casquettes.
    litellm_url: str = "http://localhost:4000"
    litellm_api_key: SecretStr = SecretStr("")
    # Orchestrateur : délai entre deux tours, et avant de réessayer un travail en échec (secondes).
    orchestrator_interval: float = 5
    orchestrator_retry_delay: float = 60

    @property
    def oidc_jwks_url(self) -> str:
        return f"{self.oidc_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
