import json
import random
from services.db import get_conn

CLUSTERS = {
    "nyc_tech_worker": {
        "label": "NYC Tech Worker",
        "description": "25-35, urban, works in tech/AI, college educated, politically liberal, high income",
        "age_range": [25, 35],
        "locations": ["New York", "San Francisco", "Seattle", "Boston"],
        "interests": ["AI", "gaming", "startups", "crypto", "fitness", "travel"],
        "political_lean": "liberal",
        "news_topics": ["artificial intelligence", "tech industry", "Democratic politics", "NYC cost of living", "gaming"],
        "media_platforms": ["YouTube", "Reddit", "Twitter", "TikTok"],
        "income_bracket": "high",
        "color": "#5856D6"
    },
    "suburban_parent": {
        "label": "Suburban Parent",
        "description": "35-50, suburban, family-focused, moderate politics, mid income",
        "age_range": [35, 50],
        "locations": ["Chicago suburbs", "Dallas suburbs", "Phoenix", "Atlanta"],
        "interests": ["parenting", "home improvement", "cooking", "family travel", "personal finance"],
        "political_lean": "moderate",
        "news_topics": ["education", "housing market", "family", "local news", "economy"],
        "media_platforms": ["YouTube", "Facebook", "Instagram"],
        "income_bracket": "mid",
        "color": "#34C759"
    },
    "college_student": {
        "label": "College Student",
        "description": "18-24, campus life, entertainment-focused, progressive, low income",
        "age_range": [18, 24],
        "locations": ["Various US college towns"],
        "interests": ["gaming", "music", "social media", "movies", "sports", "fashion"],
        "political_lean": "progressive",
        "news_topics": ["student debt", "social justice", "entertainment", "gaming", "music"],
        "media_platforms": ["TikTok", "Instagram", "YouTube", "Twitch"],
        "income_bracket": "low",
        "color": "#FF9500"
    },
    "midwest_tradesperson": {
        "label": "Midwest Tradesperson",
        "description": "30-55, rural/suburban midwest, practical, conservative, mid income",
        "age_range": [30, 55],
        "locations": ["Ohio", "Michigan", "Wisconsin", "Indiana", "Missouri"],
        "interests": ["sports", "hunting", "trucks", "country music", "local sports teams"],
        "political_lean": "conservative",
        "news_topics": ["manufacturing", "Republican politics", "NFL", "local economy", "energy"],
        "media_platforms": ["YouTube", "Facebook", "local news"],
        "income_bracket": "mid",
        "color": "#FF3B30"
    },
    "coastal_creative": {
        "label": "Coastal Creative",
        "description": "25-40, LA/NYC, works in media/arts/marketing, culturally plugged in",
        "age_range": [25, 40],
        "locations": ["Los Angeles", "New York", "Miami", "Portland"],
        "interests": ["film", "music", "art", "fashion", "food", "wellness"],
        "political_lean": "liberal",
        "news_topics": ["entertainment industry", "culture", "fashion", "wellness", "streaming"],
        "media_platforms": ["Instagram", "TikTok", "YouTube", "Spotify"],
        "income_bracket": "mid-high",
        "color": "#AF52DE"
    },
    "video_game_enthusiast": {
        "label": "Video Game Enthusiast",
        "description": "18-35, passionate gamer across PC and console, follows gaming news closely, spends heavily on games and hardware",
        "age_range": [18, 35],
        "locations": ["Various US cities", "Suburban areas"],
        "interests": ["PC gaming", "console gaming", "esports", "game reviews", "game streaming", "Twitch", "hardware", "RPGs", "FPS games"],
        "political_lean": "mixed",
        "news_topics": ["video games", "PC gaming hardware", "esports", "game releases", "Steam", "PlayStation", "Xbox"],
        "media_platforms": ["YouTube", "Twitch", "Reddit", "Discord"],
        "income_bracket": "mid",
        "color": "#00C7BE"
    }
}

FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn", "Avery", "Blake",
               "Sam", "Jamie", "Chris", "Pat", "Lee", "Dana", "Skyler", "Reese", "Sage", "River"]
LAST_NAMES  = ["Johnson", "Smith", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Moore"]

def seed_personas_if_empty(n_per_cluster=10):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM personas")
    row = cur.fetchone()
    if row["cnt"] > 0:
        print(f"Personas already seeded ({row['cnt']} records).")
        cur.close(); conn.close()
        return

    print("Seeding personas...")
    for cluster_id, cluster in CLUSTERS.items():
        for i in range(n_per_cluster):
            cur.execute("""
                INSERT INTO personas
                  (persona_id, cluster_id, cluster_label, name, age, location,
                   interests, political_lean, news_topics, media_platforms,
                   income_bracket, description)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (persona_id) DO NOTHING
            """, (
                f"{cluster_id}_{i}",
                cluster_id,
                cluster["label"],
                f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                random.randint(*cluster["age_range"]),
                random.choice(cluster["locations"]),
                json.dumps(cluster["interests"]),
                cluster["political_lean"],
                json.dumps(cluster["news_topics"]),
                json.dumps(cluster["media_platforms"]),
                cluster["income_bracket"],
                cluster["description"],
            ))
    conn.commit()
    cur.close(); conn.close()
    print(f"Seeded {len(CLUSTERS) * n_per_cluster} personas.")

def get_personas_for_cluster(cluster_id):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM personas WHERE cluster_id = %s LIMIT 20", (cluster_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

def get_all_cluster_ids():
    return list(CLUSTERS.keys())
