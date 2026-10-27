from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from synapse_api.auth import User
from synapse_api.config import get_settings
from synapse_api.routes import projects, tasks
from synapse_api.schemas import MeOut


def create_app() -> FastAPI:
    app = FastAPI(title="Synapse API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(projects.router)
    app.include_router(tasks.router)

    @app.get("/health", tags=["système"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me", response_model=MeOut, tags=["système"])
    def me(user: User) -> MeOut:
        return MeOut(subject=user.subject, name=user.name, email=user.email, roles=sorted(user.roles))

    return app


app = create_app()
