import os
import sqlalchemy
from sqlalchemy import create_engine, text, inspect
import pandas as pd
from datetime import datetime

# Database Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "goods.db")

# Use DATABASE_URL if set, otherwise default to SQLite
raw_db_url = os.getenv("DATABASE_URL")
DATABASE_URL = None

if raw_db_url:
    # Clean up quotes/backticks if present in env var
    DATABASE_URL = raw_db_url.strip().strip("'").strip('"').strip('`')

if not DATABASE_URL:
    # SQLAlchemy SQLite path requires specific formatting
    # 3 slashes for relative, 4 for absolute (Unix/Mac), or driver specific for Windows
    # For simplicity, we'll use the absolute path
    DATABASE_URL = f"sqlite:///{DB_PATH}"

print(f"Connecting to database: {DATABASE_URL}")

engine = create_engine(DATABASE_URL)

def get_connection():
    return engine.connect()

def is_postgres():
    return "postgresql" in str(engine.url)

def init_tables():
    with engine.connect() as conn:
        # Task Status Table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                running INTEGER NOT NULL,
                task_name TEXT,
                message TEXT,
                progress INTEGER,
                pid INTEGER,
                updated_at TEXT
            )
        """))
        
        # Config Table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """))
        
        # Initialize task_status if empty
        # Use dialect-specific UPSERT/IGNORE
        if is_postgres():
            conn.execute(text("""
                INSERT INTO task_status (id, running, task_name, message, progress, pid, updated_at) 
                VALUES (1, 0, NULL, '', 0, NULL, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """), {"updated_at": datetime.utcnow().isoformat()})
        else:
            conn.execute(text("""
                INSERT OR IGNORE INTO task_status (id, running, task_name, message, progress, pid, updated_at) 
                VALUES (1, 0, NULL, '', 0, NULL, :updated_at)
            """), {"updated_at": datetime.utcnow().isoformat()})
            
        conn.commit()

def ensure_columns(table_name: str, columns: list):
    inspector = inspect(engine)
    existing_cols = [col['name'] for col in inspector.get_columns(table_name)]
    
    with engine.connect() as conn:
        for col in columns:
            if col not in existing_cols:
                # SQLite and Postgres support ADD COLUMN
                # But we need to be careful with types. Defaulting to TEXT for simplicity as per original code.
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" TEXT'))
        conn.commit()

def upsert_config(key: str, value: str):
    with engine.connect() as conn:
        if is_postgres():
            conn.execute(text("""
                INSERT INTO config (key, value) VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """), {"key": key, "value": value})
        else:
            conn.execute(text("""
                INSERT INTO config (key, value) VALUES (:key, :value)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """), {"key": key, "value": value})
        conn.commit()
