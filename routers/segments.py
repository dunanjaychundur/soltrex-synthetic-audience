from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.db import get_conn

router = APIRouter()

class SegmentQuery(BaseModel):
    age_min:               Optional[int]  = 18
    age_max:               Optional[int]  = 99
    sex:                   Optional[str]  = None
    state:                 Optional[str]  = None
    education:             Optional[str]  = None
    income_level:          Optional[str]  = None
    occupation_keywords:   Optional[str]  = None
    interest_keywords:     Optional[str]  = None
    political_affiliation: Optional[str]  = None
    limit:                 Optional[int]  = 50

@router.post("/query")
def query_segment(q: SegmentQuery):
    conn = get_conn()
    cur  = conn.cursor()

    conditions = ["age >= %s", "age <= %s"]
    params     = [q.age_min, q.age_max]

    if q.sex:
        conditions.append("LOWER(sex) = LOWER(%s)")
        params.append(q.sex)

    if q.state:
        conditions.append("LOWER(state) = LOWER(%s)")
        params.append(q.state)

    if q.education:
        conditions.append("LOWER(education) ILIKE %s")
        params.append(f"%{q.education.lower()}%")

    if q.income_level:
        conditions.append("LOWER(income_level) ILIKE %s")
        params.append(f"%{q.income_level.lower()}%")

    if q.occupation_keywords:
        keywords = [k.strip() for k in q.occupation_keywords.split(",")]
        occ_conditions = " OR ".join(["LOWER(occupation) ILIKE %s"] * len(keywords))
        conditions.append(f"({occ_conditions})")
        params.extend([f"%{k.lower()}%" for k in keywords])

    if q.interest_keywords:
        keywords = [k.strip() for k in q.interest_keywords.split(",")]
        int_conditions = " OR ".join([
            "(LOWER(hobbies_and_interests) ILIKE %s OR LOWER(persona) ILIKE %s)"
        ] * len(keywords))
        conditions.append(f"({int_conditions})")
        for k in keywords:
            params.extend([f"%{k.lower()}%", f"%{k.lower()}%"])

    if q.political_affiliation:
        conditions.append("LOWER(political_affiliation) ILIKE %s")
        params.append(f"%{q.political_affiliation.lower()}%")

    where = " AND ".join(conditions)

    # Get total count
    cur.execute(f"SELECT COUNT(*) as cnt FROM nemotron_personas WHERE {where}", params)
    total = cur.fetchone()["cnt"]

    # Get sample
    cur.execute(f"""
        SELECT persona_id, age, sex, state, city, education, occupation,
               income_level, political_affiliation, hobbies_and_interests,
               skills_and_expertise, career_goals_and_ambitions, persona
        FROM nemotron_personas
        WHERE {where}
        ORDER BY RANDOM()
        LIMIT %s
    """, params + [q.limit])

    personas = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return {
        "total_matched": total,
        "returned":      len(personas),
        "personas":      personas
    }

@router.get("/saved")
def get_saved_segments():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_segments (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            criteria   TEXT,
            count      INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.execute("SELECT * FROM saved_segments ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"segments": rows}
