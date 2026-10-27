from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from synapse_api.auth import CurrentUser, get_current_user
from synapse_api.db.models import Base
from synapse_api.db.session import get_session
from synapse_api.domain.enums import Role
from synapse_api.main import create_app

PO = CurrentUser("po-1", "Aline Mbarga", "aline@orion.cm", frozenset({Role.PO}))
TESTEUR = CurrentUser("qa-1", "Brice Nkoulou", "brice@orion.cm", frozenset({Role.TESTEUR}))
AUTRE_TESTEUR = CurrentUser("qa-2", "Autre testeur", None, frozenset({Role.TESTEUR}))
ADMIN = CurrentUser("admin-1", "Admin", None, frozenset({Role.ADMIN}))


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class Clients:
    """Un client HTTP par utilisateur : `clients.as_(PO).post(...)`."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def as_(self, user: CurrentUser) -> TestClient:
        app = create_app()

        def session() -> Iterator[Session]:
            with self.session_factory() as s:
                yield s

        app.dependency_overrides[get_session] = session
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)


@pytest.fixture
def clients(session_factory: sessionmaker[Session]) -> Clients:
    return Clients(session_factory)
