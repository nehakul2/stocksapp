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


class Watchlist(Base):
    """A named list of tickers. Every user has at least one."""
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WatchlistTicker(Base):
    __tablename__ = "watchlist_tickers"
    __table_args__ = (UniqueConstraint("watchlist_id", "ticker"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer, default=0)


class Alert(Base):
    """One alert rule on one ticker of one watchlist.
    type: price_above | price_below | sma_cross_above | sma_cross_below
    value: the price, or the SMA window (5, 20, 50, 100, 200)."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(20))
    value: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AlertEvent(Base):
    """History of alerts that fired. One row per user, watchlist name, day and message,
    so checking again the same day doesn't add duplicates."""
    __tablename__ = "alert_events"
    __table_args__ = (UniqueConstraint("user_id", "watchlist_name", "day", "message"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    watchlist_name: Mapped[str] = mapped_column(String(40))
    ticker: Mapped[str] = mapped_column(String(20))
    day: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UserSettings(Base):
    """Per-user switches. A user with no row has everything at its default (off)."""
    __tablename__ = "user_settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_alerts: Mapped[bool] = mapped_column(default=False)


class AlertPause(Base):
    """An alert the user has switched off. No row means the alert is on. Kept in its own
    table because create_all can add tables but cannot add a column to an existing one."""
    __tablename__ = "alert_pauses"
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)


class AlertEmail(Base):
    """Marks an alert as 'already emailed while it keeps firing'. The row is removed when
    the alert stops firing, so it can email again if it fires later."""
    __tablename__ = "alert_emails"
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiUsage(Base):
    """How many AI requests a user has made on a given day (UTC). user_id 0 is the
    shared counter for everyone, used as a global spending cap."""
    __tablename__ = "ai_usage"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    day: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
