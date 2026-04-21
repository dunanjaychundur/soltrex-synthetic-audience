import feedparser
import json
import urllib.parse
from datetime import datetime
from services.db import get_conn
from services.persona_store import CLUSTERS

def build_rss_url(topic):
    encoded = urllib.parse.quote(topic)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

def fetch_news_for_topic(topic, max_items=3):
    url = build_rss_url(topic)
    try:
        feed  = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "title":   entry.get("title", ""),
                "summary": entry.get("summary", "")[:300],
            })
        return items
    except Exception as e:
        print(f"News fetch error for '{topic}': {e}")
        return []

def news_to_memory(item):
    return f"You came across this story: '{item['title']}'. {item.get('summary','')[:200]}"

def refresh_news_for_all_clusters():
    conn  = get_conn()
    cur   = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    inserted = 0

    for cluster_id, cluster in CLUSTERS.items():
        cur.execute(
            "SELECT COUNT(*) as cnt FROM persona_memories WHERE cluster_id=%s AND memory_date=%s",
            (cluster_id, today)
        )
        if cur.fetchone()["cnt"] > 0:
            print(f"News already refreshed today for {cluster_id}")
            continue

        for topic in cluster["news_topics"][:3]:
            items = fetch_news_for_topic(topic, max_items=2)
            for item in items:
                cur.execute("""
                    INSERT INTO persona_memories (cluster_id, memory_text, topic, headline, memory_date)
                    VALUES (%s, %s, %s, %s, %s)
                """, (cluster_id, news_to_memory(item), topic, item["title"][:200], today))
                inserted += 1

    conn.commit()
    cur.close(); conn.close()
    return {"inserted_memories": inserted, "date": today}

def get_cluster_news_context(cluster_id, limit=6):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT memory_text FROM persona_memories
        WHERE cluster_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (cluster_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    if not rows:
        return "No recent news context available for this segment."
    return "\n".join(f"- {r['memory_text']}" for r in rows)
