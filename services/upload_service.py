import os
import sys
import re
import subprocess
import tempfile
import json

def extract_frames(video_path: str, output_dir: str, interval_seconds: int = 30) -> list[str]:
    """Extract frames from video at regular intervals using ffmpeg."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval_seconds}",
        "-q:v", "2",
        f"{output_dir}/frame_%04d.jpg",
        "-y", "-loglevel", "error"
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)
    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith('.jpg')
    ])
    return frames

def transcribe_video(video_path: str) -> str:
    """Transcribe video audio using OpenAI Whisper."""
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(video_path, fp16=False)
        return result.get("text", "").strip()[:3000]
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return ""

def get_video_metadata(video_path: str) -> dict:
    """Get video duration and basic metadata via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        return {"duration": int(duration)}
    except Exception:
        return {"duration": 0}

def process_uploaded_video(file_path: str, filename: str) -> dict:
    """
    Main entry point — process an uploaded video file.
    Returns same structure as YouTube video_data.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata  = get_video_metadata(file_path)
        transcript = transcribe_video(file_path)
        frames    = extract_frames(file_path, tmpdir, interval_seconds=30)

        return {
            "title":       filename,
            "channel":     "Uploaded content",
            "duration":    metadata.get("duration", 0),
            "view_count":  None,
            "like_count":  None,
            "description": f"Uploaded video: {filename}",
            "categories":  [],
            "tags":        [],
            "thumbnail":   None,
            "transcript":  transcript,
            "upload_date": "",
            "url":         f"upload://{filename}",
            "source":      "upload",
            "frame_count": len(frames)
        }
