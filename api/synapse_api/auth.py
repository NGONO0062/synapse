"""Identité : jetons OIDC émis par Keycloak, rôles PO / TESTEUR / ADMIN."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from synapse_api.config import get_settings
from synapse_api.domain.enums import Role
from synapse_api.domain.lifecycle import Actor

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    subject: str
    name: str
    email: str | None
    roles: frozenset[Role]

    def has(self, role: Role) -> bool:
        return role in self.roles

    def as_actor(self) -> Actor:
        return Actor.human(self.name, *self.roles)


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().oidc_jwks_url, cache_keys=True)


def user_from_claims(claims: dict) -> CurrentUser:
    raw_roles = claims.get("realm_access", {}).get("roles", [])
    roles = frozenset(Role(r) for r in raw_roles if r in Role.__members__)
    return CurrentUser(
        subject=claims["sub"],
        name=claims.get("name") or claims.get("preferred_username") or claims["sub"],
        email=claims.get("email"),
        roles=roles,
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.")
    settings = get_settings()
    try:
        key = _jwks_client().get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide.") from exc
    return user_from_claims(claims)


User = Annotated[CurrentUser, Depends(get_current_user)]


def require_any(user: CurrentUser, *roles: Role) -> None:
    if not any(user.has(r) for r in roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès refusé pour ce rôle.")
