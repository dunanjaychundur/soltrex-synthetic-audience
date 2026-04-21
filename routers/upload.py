from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from services.upload_service import process_uploaded_video
from services.youtube_service import classify_video_topics, match_clusters_to_video
from services.reaction_engine import run_full_analysis, run_nemotron_analysis, save_analysis
import tempfile
import os
import json

router = APIRouter()

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
MAX_FILE_SIZE_MB   = 200

@router.post("/video")
async def upload_video(
    file:              UploadFile = File(...),
    cluster_ids:       str        = Form(default=""),
    nemotron_segments: str        = Form(default=""),
    mode:              str        = Form(default="clusters")
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Use MP4, MOV, or WebM.")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_FILE_SIZE_MB}MB.")
        tmp.write(content)
        tmp_path = tmp.name

    try:
        video_data   = process_uploaded_video(tmp_path, file.filename or "upload")
        video_topics = classify_video_topics(video_data)

        if mode == "nemotron" and nemotron_segments:
            segments = json.loads(nemotron_segments)
            result   = run_nemotron_analysis(video_data, segments)
            result["mode"] = "nemotron"
        else:
            ids      = json.loads(cluster_ids) if cluster_ids else match_clusters_to_video(video_topics)
            result   = run_full_analysis(video_data, ids)
            result["mode"] = "clusters"

        result["detected_topics"] = video_topics

        try:
            save_analysis(video_data, result)
        except Exception as e:
            print(f"Could not save analysis: {e}")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)
