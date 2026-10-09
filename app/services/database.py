import json
from datetime import datetime, timezone
from typing import Generator, Optional
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class FileRecord(Base):
    __tablename__ = "files"

    id = Column(String(64), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    feature_count = Column(Integer, default=0, nullable=False)
    crs = Column(String(128), default="EPSG:4326", nullable=False)
    status = Column(String(32), default="PENDING", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    processing_time_ms = Column(Float, nullable=True)
    summary_json = Column(Text, nullable=True)
    features_json = Column(Text, nullable=True)

    def get_summary(self) -> Optional[dict]:
        if self.summary_json:
            try:
                return json.loads(self.summary_json)
            except Exception:
                return None
        return None

    def get_features(self) -> list:
        if self.features_json:
            try:
                return json.loads(self.features_json)
            except Exception:
                return []
        return []


def init_db():
    Base.metadata.create_all(bind=engine)


# Auto-create tables on startup
init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
