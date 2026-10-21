from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import session_factory, build_engine
from app.config import Settings
from app.models import Product  # Assumes your models are defined here


# Dependency to get the database session
def get_db():
    settings = Settings()
    engine = build_engine(settings.database_url)
    SessionLocal = session_factory(engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/products", tags=["Products & Suppliers"])


@router.get("/")
def get_all_products(db: Session = Depends(get_db)):
    """Fetches all products from the database."""
    products = db.query(Product).all()
    return products
