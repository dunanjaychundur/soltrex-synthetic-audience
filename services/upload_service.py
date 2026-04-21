import os
import subprocess
import tempfile
import json
import base64

def extract_frames(video_path: str, output_dir: str, interval_seconds: int = 10, max_frames: int = 8) -> list:
    """Extract frames at intervals, capped at max_frames."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval_seconds},scale=640:-1",
        "-q:v", "3",
        f"{output_dir}/frame_%04d.jpg",
        "-y", "-loglevel", "error"
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)
    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith('.jpg')
    ])
    return frames[:max_frames]

def frames_to_base64(frame_paths: list) -> list:
    """Convert frame images to base64 strings."""
    encoded = []
    for path in frame_paths:
        try:
            with open(path, "rb") as f:
                encoded.append(base64.b64encode(f.read()).decode("utf-8"))
        except Exception as e:
            print(f"Frame encode error: {e}")
    return encoded

def transcribe_video(video_path: str) -> str:
    """Transcribe using OpenAI Whisper API."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("OPENAI_API_KEY not set — skipping transcription.")
        return ""

    audio_path = video_path + ".mp3"
    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
            audio_path, "-y", "-loglevel", "error"
        ], capture_output=True, timeout=120)

        import httpx
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_key}"},
            files={"file": ("audio.mp3", audio_data, "audio/mpeg")},
            data={"model": "whisper-1"},
            timeout=120
        )

        if response.status_code == 200:
            return response.json().get("text", "")[:3000]
        else:
            print(f"Whisper API error: {response.status_code} {response.text[:200]}")
            return ""

    except Exception as e:
        print(f"Transcription error: {e}")
        return ""
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)

def get_video_metadata(video_path: str) -> dict:
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", video_path
        ], capture_output=True, text=True, timeout=30)
        data     = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        return {"duration": int(duration)}
    except Exception:
        return {"duration": 0}

def process_uploaded_video(file_path: str, filename: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata   = get_video_metadata(file_path)
        transcript = transcribe_video(file_path)
        frames     = extract_frames(file_path, tmpdir)
        frame_b64  = frames_to_base64(frames)

    print(f"Processed: {filename} | duration={metadata.get('duration')}s | transcript_len={len(transcript)} | frames={len(frame_b64)}")

    return {
        "title":       filename,
        "channel":     "Uploaded content",
        "duration":    metadata.get("duration", 0),
        "view_count":  None,
        "like_count":  None,
        "description": "",
        "categories":  [],
        "tags":        [],
        "thumbnail":   None,
        "transcript":  transcript,
        "upload_date": "",
        "url":         f"upload://{filename}",
        "source":      "upload",
        "frames_b64":  frame_b64,
    }
