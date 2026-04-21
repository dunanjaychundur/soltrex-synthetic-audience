"""
One-time script to load Nvidia Nemotron-Personas-USA into your Postgres database.

Usage:
  set DATABASE_URL=postgresql://xata:password@....xata.tech/postgres?sslmode=require
  set HF_TOKEN=hf_...
  python ingest_nemotron.py --limit 50000
"""

import os
import sys
import json
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

def get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("Missing DATABASE_URL environment variable.")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)

def setup_nemotron_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nemotron_personas (
            id                          SERIAL PRIMARY KEY,
            persona_id                  TEXT UNIQUE,
            age                         INT,
            sex                         TEXT,
            state                       TEXT,
            city                        TEXT,
            education                   TEXT,
            occupation                  TEXT,
            marital_status              TEXT,
            race_ethnicity              TEXT,
            income_level                TEXT,
            political_affiliation       TEXT,
            hobbies_and_interests       TEXT,
            skills_and_expertise        TEXT,
            career_goals_and_ambitions  TEXT,
            persona                     TEXT,
            raw_fields                  TEXT,
            created_at                  TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_nemotron_state
            ON nemotron_personas(state);
        CREATE INDEX IF NOT EXISTS idx_nemotron_age
            ON nemotron_personas(age);
        CREATE INDEX IF NOT EXISTS idx_nemotron_occupation
            ON nemotron_personas(occupation);
        CREATE INDEX IF NOT EXISTS idx_nemotron_education
            ON nemotron_personas(education);
    """)

    conn.commit()
    cur.close()
    print("nemotron_personas table ready.")

def extract_fields(record: dict, index: int) -> dict:
    """
    Map Nemotron record fields to our schema.
    Field names may vary slightly — we try common variants.
    """
    def get(*keys):
        for k in keys:
            v = record.get(k) or record.get(k.lower()) or record.get(k.upper())
            if v:
                return str(v).strip()
        return None

    # Store all raw fields as JSON for future use
    raw = {k: str(v)[:500] for k, v in record.items() if v}

    return {
        "persona_id":                  f"nemotron_{index}",
        "age":                         int(record.get("age", 0) or 0),
        "sex":                         get("sex", "gender"),
        "state":                       get("state", "State"),
        "city":                        get("city", "City", "location"),
        "education":                   get("education", "education_level", "Education"),
        "occupation":                  get("occupation", "Occupation", "job"),
        "marital_status":              get("marital_status", "MaritalStatus"),
        "race_ethnicity":              get("race_ethnicity", "race", "ethnicity"),
        "income_level":                get("income_level", "income", "Income"),
        "political_affiliation":       get("political_affiliation", "political_lean", "politics"),
        "hobbies_and_interests":       get("hobbies_and_interests", "hobbies", "interests"),
        "skills_and_expertise":        get("skills_and_expertise", "skills"),
        "career_goals_and_ambitions":  get("career_goals_and_ambitions", "career_goals"),
        "persona":                     get("persona", "description", "bio"),
        "raw_fields":                  json.dumps(raw)[:5000],
    }

def ingest(limit: int = 50000, batch_size: int = 500):
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("Warning: HF_TOKEN not set. Set it if the dataset requires authentication.")

    print(f"Loading Nemotron dataset (streaming, limit={limit})...")

    try:
        from datasets import load_dataset
        ds = load_dataset(
            "nvidia/Nemotron-Personas-USA",
            split="train",
            streaming=True,
            token=hf_token
        )
    except Exception as e:
        raise Exception(f"Failed to load dataset: {e}")

    conn = get_conn()
    setup_nemotron_table(conn)

    cur = conn.cursor()

    # Check how many already exist
    cur.execute("SELECT COUNT(*) as cnt FROM nemotron_personas")
    existing = cur.fetchone()["cnt"]
    if existing > 0:
        print(f"{existing} records already in database.")
        answer = input("Continue and add more? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            cur.close(); conn.close()
            return

    print(f"Ingesting up to {limit} records in batches of {batch_size}...")

    batch = []
    total = 0
    skipped = 0

    for i, record in enumerate(ds):
        if total >= limit:
            break

        try:
            row = extract_fields(record, i + existing)
            batch.append(row)
        except Exception as e:
            skipped += 1
            continue

        if len(batch) >= batch_size:
            _insert_batch(cur, conn, batch)
            total += len(batch)
            batch = []
            print(f"  Inserted {total} records...", end="\r")

    if batch:
        _insert_batch(cur, conn, batch)
        total += len(batch)

    cur.close()
    conn.close()

    print(f"\nDone. Inserted {total} records. Skipped {skipped}.")
    print("You can now query nemotron_personas to build segments.")

def _insert_batch(cur, conn, batch: list):
    execute_batch(cur, """
        INSERT INTO nemotron_personas (
            persona_id, age, sex, state, city, education, occupation,
            marital_status, race_ethnicity, income_level, political_affiliation,
            hobbies_and_interests, skills_and_expertise,
            career_goals_and_ambitions, persona, raw_fields
        ) VALUES (
            %(persona_id)s, %(age)s, %(sex)s, %(state)s, %(city)s,
            %(education)s, %(occupation)s, %(marital_status)s,
            %(race_ethnicity)s, %(income_level)s, %(political_affiliation)s,
            %(hobbies_and_interests)s, %(skills_and_expertise)s,
            %(career_goals_and_ambitions)s, %(persona)s, %(raw_fields)s
        )
        ON CONFLICT (persona_id) DO NOTHING
    """, batch)
    conn.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Nemotron personas into Postgres")
    parser.add_argument("--limit", type=int, default=50000, help="Max records to ingest (default 50000)")
    parser.add_argument("--batch-size", type=int, default=500, help="Insert batch size (default 500)")
    args = parser.parse_args()
    ingest(limit=args.limit, batch_size=args.batch_size)
