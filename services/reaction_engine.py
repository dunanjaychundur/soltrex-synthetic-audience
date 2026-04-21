import anthropic
import json
import re
from services.persona_store import CLUSTERS
from services.news_service import get_cluster_news_context
from services.db import get_conn

client = anthropic.Anthropic()

def generate_cluster_reaction(cluster_id, video_data):
    cluster      = CLUSTERS[cluster_id]
    news_context = get_cluster_news_context(cluster_id, limit=6)
    transcript   = (video_data.get("transcript") or "")[:1500] or (video_data.get("description") or "")[:500]

    prompt = f"""You are simulating how a real person from this demographic reacts to a YouTube video.

PERSONA SEGMENT: {cluster['label']}
Profile: {cluster['description']}
Interests: {', '.join(cluster['interests'])}
Political lean: {cluster['political_lean']}
Platforms they use: {', '.join(cluster['media_platforms'])}

RECENT NEWS THIS PERSON HAS BEEN EXPOSED TO:
{news_context}

VIDEO THEY JUST WATCHED:
Title: {video_data.get('title', '')}
Channel: {video_data.get('channel', '')}
Duration: {video_data.get('duration', 0)} seconds
Description: {(video_data.get('description') or '')[:300]}
Transcript excerpt: {transcript}

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "watch_completion": <0-100>,
  "engagement_score": <0-100>,
  "sentiment": "<positive|neutral|negative|polarised>",
  "would_share": <true|false>,
  "would_subscribe": <true|false>,
  "simulated_comment": "<what this person would actually comment, 1-2 sentences>",
  "drop_off_point": "<immediate|first_30s|first_minute|halfway|completion>",
  "reaction_summary": "<2-3 sentences on how this segment genuinely feels>",
  "key_resonance": "<one thing that connected most, or null>",
  "key_friction": "<one thing that put them off most, or null>"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "watch_completion": 50, "engagement_score": 30,
            "sentiment": "neutral", "would_share": False,
            "would_subscribe": False, "simulated_comment": "Interesting.",
            "drop_off_point": "halfway", "reaction_summary": "Mixed reaction.",
            "key_resonance": None, "key_friction": None
        }

    result["cluster_id"]    = cluster_id
    result["cluster_label"] = cluster["label"]
    result["cluster_color"] = cluster["color"]
    return result

def save_analysis(video_data, result):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO analysis_results
          (youtube_url, video_title, video_channel, real_views, real_likes,
           detected_topics, summary, reactions)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        video_data.get("url", ""),
        video_data.get("title", ""),
        video_data.get("channel", ""),
        video_data.get("view_count") or 0,
        video_data.get("like_count") or 0,
        json.dumps(result.get("detected_topics", [])),
        json.dumps(result.get("summary", {})),
        json.dumps(result.get("segment_reactions", [])),
    ))
    conn.commit()
    cur.close(); conn.close()

def run_full_analysis(video_data, cluster_ids):
    reactions = []
    for cluster_id in cluster_ids:
        try:
            reactions.append(generate_cluster_reaction(cluster_id, video_data))
        except Exception as e:
            print(f"Reaction error for {cluster_id}: {e}")

    if not reactions:
        return {"error": "No reactions generated"}

    avg_watch      = sum(r["watch_completion"] for r in reactions) / len(reactions)
    avg_engagement = sum(r["engagement_score"]  for r in reactions) / len(reactions)
    sentiment_counts = {}
    for r in reactions:
        s = r["sentiment"]
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1
    dominant_sentiment = max(sentiment_counts, key=sentiment_counts.get)
    share_rate = sum(1 for r in reactions if r.get("would_share")) / len(reactions) * 100

    return {
        "video": {
            "title":      video_data.get("title"),
            "channel":    video_data.get("channel"),
            "thumbnail":  video_data.get("thumbnail"),
            "duration":   video_data.get("duration"),
            "url":        video_data.get("url"),
            "real_views": video_data.get("view_count"),
            "real_likes": video_data.get("like_count"),
        },
        "summary": {
            "avg_watch_completion": round(avg_watch, 1),
            "avg_engagement_score": round(avg_engagement, 1),
            "dominant_sentiment":   dominant_sentiment,
            "predicted_share_rate": round(share_rate, 1),
            "segments_analysed":    len(reactions)
        },
        "segment_reactions": reactions
    }
