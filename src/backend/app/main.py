from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import router
from app.config import Settings
from app.db import build_engine, session_factory
from app.services.versioning import data_version


def create_app(database_url: str | None = None):
    settings = Settings()
    engine = build_engine(database_url or settings.database_url)
    application = FastAPI(
        title=settings.app_name,
        description="Synthetic-data demonstration backend. /docs is the interactive API tester.",
        version="0.1.0",
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory(engine)

    @application.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    @application.get("/health", tags=["Setup"])
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                ready = inspect(connection).has_table("products")
        except SQLAlchemyError:
            return JSONResponse(status_code=503, content={"status": "database unavailable"})
        if not ready:
            return JSONResponse(
                status_code=503,
                content={"status": "schema missing", "next_step": "python -m alembic upgrade head"},
            )
        with application.state.session_factory() as db:
            version = data_version(db)
        return {
            "status": "ok",
            "database": "ok",
            "schema": "ready",
            "business_timezone": settings.business_timezone,
            "business_date": settings.business_today().isoformat(),
            "data_version": version,
        }

    @application.exception_handler(IntegrityError)
    def integrity_error(_request, _exc):
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Conflicting data: check duplicate identifiers and database constraints."
            },
        )

    application.include_router(router)
    return application


app = create_app()
