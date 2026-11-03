import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env')


def get_database_url() -> str:
    """Return database URL.

    Priority: `DATABASE_URL` env var. If not set, default to a local SQLite file
    so the app can run without a running MySQL server.
    """
    url = os.getenv('DATABASE_URL')
    if url:
        return url

    # Default to a local sqlite file inside the backend project
    db_path = BASE_DIR / 'database.sqlite3'
    return f'sqlite:///{db_path}'


SQLALCHEMY_DATABASE_URL = get_database_url()

# Use SQLite-specific connect args when using a sqlite file URL
if SQLALCHEMY_DATABASE_URL.startswith('sqlite'):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection():
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return True, None
    except SQLAlchemyError as exc:
        return False, str(exc)
