from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """SQLite stores naive UTC; Python/API values always carry a UTC offset."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamps must include a timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def utc_now():
    return datetime.now(timezone.utc)


def build_engine(database_url: str):
    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url, connect_args={"check_same_thread": False, "timeout": 30}
        )

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(database_url)


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def commit(db: Session):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Database constraint failed: check duplicate IDs/SKUs or related records.",
        ) from exc
