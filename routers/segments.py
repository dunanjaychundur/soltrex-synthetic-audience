from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.db import get_conn

router = APIRouter()

class SegmentQuery(BaseModel):
    age_min:             Optional[int]       = 18
    age_max:             Optional[int]       = 99
    sex:                 Optional[str]       = None
    states:              Optional[list[str]] = None
    educations:          Optional[list[str]] = None
    occupation_keywords: Optional[str]       = None
    interest_keywords:   Optional[str]       = None
    limit:               Optional[int]       = 50

@router.post("/query")
def query_segment(q: SegmentQuery):
    conn = get_conn()
    cur  = conn.cursor()

    conditions = ["age >= %s", "age <= %s"]
    params     = [q.age_min, q.age_max]

    if q.sex:
        conditions.append("LOWER(sex) = LOWER(%s)")
        params.append(q.sex)

    if q.states:
        placeholders = ",".join(["%s"] * len(q.states))
        conditions.append(f"state IN ({placeholders})")
        params.extend(q.states)

    if q.educations:
        placeholders = ",".join(["%s"] * len(q.educations))
        conditions.append(f"education IN ({placeholders})")
        params.extend(q.educations)

    if q.occupation_keywords:
        keywords = [k.strip() for k in q.occupation_keywords.split(",")]
        occ = " OR ".join(["LOWER(occupation) ILIKE %s"] * len(keywords))
        conditions.append(f"({occ})")
        params.extend([f"%{k.lower()}%" for k in keywords])

    if q.interest_keywords:
        keywords = [k.strip() for k in q.interest_keywords.split(",")]
        int_conds = " OR ".join([
            "(LOWER(hobbies_and_interests) ILIKE %s OR LOWER(persona) ILIKE %s)"
        ] * len(keywords))
        conditions.append(f"({int_conds})")
        for k in keywords:
            params.extend([f"%{k.lower()}%", f"%{k.lower()}%"])

    where = " AND ".join(conditions)

    cur.execute(f"SELECT COUNT(*) as cnt FROM nemotron_personas WHERE {where}", params)
    total = cur.fetchone()["cnt"]

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
    cur.close(); conn.close()

    return {"total_matched": total, "returned": len(personas), "personas": personas}
