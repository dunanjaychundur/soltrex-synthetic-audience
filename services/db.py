import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError(
            "Missing DATABASE_URL.\n"
            "  set DATABASE_URL=postgresql://xata:password@....xata.tech/postgres?sslmode=require\n"
        )
    return psycopg2.connect(url, cursor_factory=RealDictCursor)

def setup_schema():
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS personas (
            id               SERIAL PRIMARY KEY,
            persona_id       TEXT UNIQUE NOT NULL,
            cluster_id       TEXT NOT NULL,
            cluster_label    TEXT,
            name             TEXT,
            age              INT,
            location         TEXT,
            interests        TEXT,
            political_lean   TEXT,
            news_topics      TEXT,
            media_platforms  TEXT,
            income_bracket   TEXT,
            description      TEXT,
            created_at       TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS persona_memories (
            id           SERIAL PRIMARY KEY,
            cluster_id   TEXT NOT NULL,
            memory_text  TEXT,
            topic        TEXT,
            headline     TEXT,
            memory_date  TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analysis_results (
            id              SERIAL PRIMARY KEY,
            youtube_url     TEXT,
            video_title     TEXT,
            video_channel   TEXT,
            real_views      BIGINT,
            real_likes      BIGINT,
            detected_topics TEXT,
            summary         TEXT,
            reactions       TEXT,
            created_at      TIMESTAMP DEFAULT NOW()
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Schema ready.")
