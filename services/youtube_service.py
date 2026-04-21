import subprocess
import json
import re
import os
import sys
import tempfile

def extract_video_data(youtube_url: str) -> dict:
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json",
            "--skip-download",
            "--write-auto-sub",
            "--sub-format", "json3",
            "--no-warnings",
            youtube_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise Exception(f"yt-dlp error: {result.stderr[:200]}")

        data = json.loads(result.stdout)

        transcript = extract_transcript_from_info(data)
        if not transcript:
            transcript = extract_auto_captions(youtube_url)

        categories = data.get("categories", [])
        tags = data.get("tags", [])[:10]

        return {
            "title": data.get("title", ""),
            "channel": data.get("uploader", ""),
            "duration": data.get("duration", 0),
            "view_count": data.get("view_count", 0),
            "like_count": data.get("like_count", 0),
            "comment_count": data.get("comment_count", 0),
            "description": (data.get("description", "") or "")[:500],
            "categories": categories,
            "tags": tags,
            "thumbnail": data.get("thumbnail", ""),
            "transcript": transcript,
            "upload_date": data.get("upload_date", ""),
            "url": youtube_url
        }
    except Exception as e:
        raise Exception(f"Failed to extract video data: {str(e)}")

def extract_transcript_from_info(data: dict) -> str:
    subtitles = data.get("automatic_captions", {}) or data.get("subtitles", {})
    for lang in ["en", "en-US", "en-GB"]:
        if lang in subtitles:
            entries = subtitles[lang]
            for entry in entries:
                if entry.get("ext") == "json3":
                    return f"[Transcript available in {lang}]"
    return ""

def extract_auto_captions(youtube_url: str) -> str:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--skip-download",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "--no-warnings",
                "-o", f"{tmpdir}/%(id)s.%(ext)s",
                youtube_url
            ]
            subprocess.run(cmd, capture_output=True, timeout=60)

            for fname in os.listdir(tmpdir):
                if fname.endswith(".vtt"):
                    with open(os.path.join(tmpdir, fname)) as f:
                        raw = f.read()
                    return clean_vtt(raw)
        return ""
    except Exception:
        return ""

def clean_vtt(vtt_text: str) -> str:
    lines = vtt_text.split("\n")
    seen = set()
    clean = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"^\d+$", "", line)
        if line and line not in seen:
            seen.add(line)
            clean.append(line)
    text = " ".join(clean)
    return text[:3000]

def classify_video_topics(video_data: dict) -> list[str]:
    topics = []
    combined = " ".join([
        video_data.get("title", ""),
        video_data.get("description", ""),
        " ".join(video_data.get("tags", [])),
        " ".join(video_data.get("categories", []))
    ]).lower()

    topic_keywords = {
        "AI": ["ai", "artificial intelligence", "machine learning", "chatgpt", "llm", "openai"],
        "gaming": ["gaming", "game", "xbox", "playstation", "nintendo", "steam", "twitch"],
        "tech": ["tech", "technology", "software", "startup", "coding", "developer"],
        "fitness": ["fitness", "workout", "gym", "health", "exercise", "nutrition"],
        "finance": ["finance", "investing", "stock", "crypto", "money", "budget"],
        "entertainment": ["movie", "film", "music", "celebrity", "tv show", "netflix"],
        "politics": ["politics", "election", "government", "democrat", "republican", "policy"],
        "lifestyle": ["lifestyle", "travel", "food", "fashion", "beauty", "vlog"],
        "sports": ["sports", "football", "basketball", "nfl", "nba", "soccer"],
        "education": ["education", "learn", "tutorial", "how to", "explained", "course"]
    }

    for topic, keywords in topic_keywords.items():
        if any(kw in combined for kw in keywords):
            topics.append(topic)

    return topics if topics else ["general"]

def match_clusters_to_video(video_topics: list[str]) -> list[str]:
    from services.persona_store import CLUSTERS

    cluster_topic_map = {
        "nyc_tech_worker": ["AI", "tech", "gaming", "finance"],
        "suburban_parent": ["lifestyle", "finance", "education", "entertainment"],
        "college_student": ["gaming", "entertainment", "lifestyle", "sports"],
        "midwest_tradesperson": ["sports", "politics", "lifestyle"],
        "coastal_creative": ["entertainment", "lifestyle", "fitness", "education"],
        "video_game_enthusiast": ["gaming", "tech", "entertainment"]
    }

    matched = []
    for cluster_id, cluster_topics in cluster_topic_map.items():
        if any(vt in cluster_topics for vt in video_topics):
            matched.append(cluster_id)

    return matched if matched else list(CLUSTERS.keys())
