from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.youtube_service import extract_video_data, classify_video_topics, match_clusters_to_video
from services.reaction_engine import run_full_analysis, save_analysis
from services.db import get_conn
import json

router = APIRouter()

class AnalyzeRequest(BaseModel):
    youtube_url: str
    cluster_ids: list[str] | None = None

@router.post("/youtube")
def analyze_youtube(req: AnalyzeRequest):
    try:
        video_data = extract_video_data(req.youtube_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    video_topics = classify_video_topics(video_data)
    cluster_ids  = req.cluster_ids or match_clusters_to_video(video_topics)
    result       = run_full_analysis(video_data, cluster_ids)
    result["detected_topics"] = video_topics

    try:
        save_analysis(video_data, result)
    except Exception as e:
        print(f"Could not save analysis: {e}")

    return result

@router.get("/history")
def get_history():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM analysis_results ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()
    cur.close(); conn.close()
    records = []
    for r in dict(rows) if isinstance(rows, dict) else [dict(r) for r in rows]:
        for field in ["detected_topics", "summary", "reactions"]:
            if isinstance(r.get(field), str):
                try: r[field] = json.loads(r[field])
                except: pass
        records.append(r)
    return {"analyses": records}
