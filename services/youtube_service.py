import os
import re
import httpx

YOUTUBE_API_KEY  = os.environ.get("YOUTUBE_API_KEY")
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def extract_video_id(url: str) -> str:
    patterns = [r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise Exception(f"Could not extract video ID from URL: {url}")

def fetch_video_metadata(video_id: str) -> dict:
    if not YOUTUBE_API_KEY:
        raise Exception("YOUTUBE_API_KEY environment variable not set.")

    response = httpx.get(
        f"{YOUTUBE_API_BASE}/videos",
        params={"id": video_id, "part": "snippet,statistics,contentDetails", "key": YOUTUBE_API_KEY},
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(f"YouTube API error {response.status_code}: {response.text[:200]}")

    data  = response.json()
    items = data.get("items", [])
    if not items:
        raise Exception(f"Video not found or unavailable: {video_id}")

    item     = items[0]
    snippet  = item.get("snippet", {})
    stats    = item.get("statistics", {})
    details  = item.get("contentDetails", {})
    duration = parse_iso_duration(details.get("duration", "PT0S"))
    thumb    = (snippet.get("thumbnails", {}).get("maxres") or
                snippet.get("thumbnails", {}).get("high") or {}).get("url", "")

    return {
        "video_id":     video_id,
        "title":        snippet.get("title", ""),
        "channel":      snippet.get("channelTitle", ""),
        "description":  (snippet.get("description", "") or "")[:500],
        "tags":         snippet.get("tags", [])[:10],
        "categories":   [],
        "thumbnail":    thumb,
        "duration":     duration,
        "view_count":   int(stats.get("viewCount",  0) or 0),
        "like_count":   int(stats.get("likeCount",  0) or 0),
        "comment_count":int(stats.get("commentCount",0) or 0),
        "upload_date":  snippet.get("publishedAt", "")[:10],
    }

def fetch_transcript(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        entries = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(t["text"] for t in entries)[:3000]
    except Exception as e:
        print(f"Transcript unavailable for {video_id}: {e}")
        return ""

def parse_iso_duration(duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s

def extract_video_data(youtube_url: str) -> dict:
    video_id   = extract_video_id(youtube_url)
    metadata   = fetch_video_metadata(video_id)
    transcript = fetch_transcript(video_id)
    return {**metadata, "transcript": transcript, "url": youtube_url, "source": "youtube_api", "frames_b64": []}

def classify_video_topics(video_data: dict) -> list[str]:
    combined = " ".join([
        video_data.get("title", ""),
        video_data.get("description", ""),
        " ".join(video_data.get("tags", [])),
    ]).lower()

    topic_keywords = {
        "AI":           ["ai", "artificial intelligence", "machine learning", "chatgpt", "llm"],
        "gaming":       ["gaming", "game", "xbox", "playstation", "nintendo", "steam", "twitch"],
        "tech":         ["tech", "technology", "software", "startup", "coding", "developer"],
        "fitness":      ["fitness", "workout", "gym", "health", "exercise", "nutrition"],
        "finance":      ["finance", "investing", "stock", "crypto", "money", "budget"],
        "entertainment":["movie", "film", "music", "celebrity", "tv show", "netflix"],
        "politics":     ["politics", "election", "government", "democrat", "republican"],
        "lifestyle":    ["lifestyle", "travel", "food", "fashion", "beauty", "vlog"],
        "sports":       ["sports", "football", "basketball", "nfl", "nba", "soccer"],
        "education":    ["education", "learn", "tutorial", "how to", "explained", "course"],
    }

    topics = [t for t, kws in topic_keywords.items() if any(kw in combined for kw in kws)]
    return topics if topics else ["general"]

def match_clusters_to_video(video_topics: list[str]) -> list[str]:
    from services.persona_store import CLUSTERS
    cluster_topic_map = {
        "nyc_tech_worker":       ["AI", "tech", "gaming", "finance"],
        "suburban_parent":       ["lifestyle", "finance", "education", "entertainment"],
        "college_student":       ["gaming", "entertainment", "lifestyle", "sports"],
        "midwest_tradesperson":  ["sports", "politics", "lifestyle"],
        "coastal_creative":      ["entertainment", "lifestyle", "fitness", "education"],
        "video_game_enthusiast": ["gaming", "tech", "entertainment"],
    }
    matched = [cid for cid, topics in cluster_topic_map.items() if any(vt in topics for vt in video_topics)]
    return matched if matched else list(CLUSTERS.keys())
