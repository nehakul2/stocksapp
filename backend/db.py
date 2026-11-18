"""Database setup. Uses DATABASE_URL (Postgres on Railway/Neon); falls back to a
local SQLite file so the app runs on a laptop with no setup."""
import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    # Neon's "Connect" box can show `psql '<url>'`; accept that and quoted values too.
    if url.startswith("psql "):
        url = url[5:].strip()
    url = url.strip("'\"").strip()
    if not url:
        return "sqlite:///./stocksapp.db"
    # Providers hand out postgres:// or postgresql://; SQLAlchemy needs the driver named.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


URL = database_url()
try:
    engine = create_engine(
        URL,
        pool_pre_ping=True,  # hosted databases drop idle connections
        connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {},
    )
except Exception:
    # Don't echo the URL: it contains the database password.
    raise SystemExit(
        "DATABASE_URL is not a valid connection string. It should be one line starting with "
        "postgresql:// (no quotes, no spaces, no 'psql'). Check backend/.env."
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "ticker"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer, default=0)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
