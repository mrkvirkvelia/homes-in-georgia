from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# More connections than FastAPI's 40 worker threads: get_db's cleanup itself needs a free thread, so with a smaller pool a
# burst of photo requests (site + CRM thumbnails) left every thread waiting for a connection nobody could return (deadlock).
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True, pool_size=10, max_overflow=40, pool_timeout=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    # used as Depends(get_db, scope="function"): closed when the endpoint returns, not after the response is sent,
    # so a slow download (photos over a tunnel/mobile) never holds a pool connection
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
