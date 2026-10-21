import csv
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from app.db import build_engine, session_factory
from app.config import Settings
from app.models import Product, Batch, StockMovement


def export_table_to_csv(db: Session, model, filename: str):
    """Exports a given SQLAlchemy model's data to a CSV file."""
    records = db.query(model).all()

    if not records:
        print(f"No records found for {model.__tablename__}.")
        return

    # Extract column headers from the SQLAlchemy model
    headers = [column.name for column in model.__table__.columns]

    filepath = Path(filename)
    with filepath.open(mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers)

        for record in records:
            writer.writerow([getattr(record, column) for column in headers])

    print(f"Successfully exported {model.__tablename__} to {filename}")


def main():
    settings = Settings()
    engine = build_engine(settings.database_url)
    SessionLocal = session_factory(engine)
    db = SessionLocal()

    try:
        # Export core tables required by the plan
        export_table_to_csv(db, Product, "export_products.csv")
        export_table_to_csv(db, Batch, "export_batches.csv")
        export_table_to_csv(db, StockMovement, "export_movements.csv")
        print("CSV export complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
