from functools import lru_cache
from pathlib import Path

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
    # Modèle des tâches créées sans choix explicite (bug signalé, formulaire). Un des AI_MODELS.
    default_ai_model: str = "claude-sonnet"
    # Quota mensuel de consommation IA par projet (dollars) quand l'administrateur n'en a pas fixé
    # pour le projet. Vide : pas de quota.
    project_monthly_budget_usd: float | None = None
    # Catalogue de la passerelle (modèle réel et prix de chaque nom), relu après ce délai (secondes).
    model_catalog_ttl: float = 600
    # Cas de référence rejoués automatiquement par l'orchestrateur quand le modèle réel, les consignes
    # ou les cas changent. À couper si les appels sont comptés au plus juste (offre gratuite).
    evaluations: bool = True
    # Orchestrateur : délai entre deux tours, et avant de réessayer un travail en échec (secondes).
    orchestrator_interval: float = 5
    orchestrator_retry_delay: float = 60

    # Dépôts Git des projets et copies de travail des tâches (lot 3b).
    git_dir: Path = Path("var")
    # Bac à sable : un conteneur jetable par commande, propre à la tâche, sans réseau ni secret.
    sandbox_image: str = "node:22-bookworm"  # si le dépôt ne déclare pas le sien (synapse.json)
    sandbox_cpus: str = "2"
    sandbox_memory: str = "2g"
    sandbox_timeout: int = 900  # secondes par commande

    @property
    def oidc_jwks_url(self) -> str:
        return f"{self.oidc_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
