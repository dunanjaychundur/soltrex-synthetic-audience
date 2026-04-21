import anthropic
import json
import re
import random
from services.persona_store import CLUSTERS
from services.news_service import get_cluster_news_context
from services.db import get_conn

client = anthropic.Anthropic()
COLORS = ["#5856D6","#34C759","#FF9500","#FF3B30","#AF52DE","#00C7BE","#FF2D55","#0A84FF"]

def _call_claude(prompt, frames_b64=None):
    """Call Claude with optional vision frames."""
    if frames_b64:
        # Build multimodal message with frames + text
        content = []
        for i, b64 in enumerate(frames_b64[:6]):
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
            })
        content.append({"type": "text", "text": f"Above are {len(frames_b64[:6])} frames sampled from the video.\n\n{prompt}"})
    else:
        content = prompt

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )
    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "watch_completion": 50, "engagement_score": 30,
            "sentiment": "neutral", "would_share": False,
            "would_subscribe": False, "simulated_comment": "Interesting.",
            "drop_off_point": "halfway", "reaction_summary": "Mixed reaction.",
            "key_resonance": None, "key_friction": None
        }

def generate_cluster_reaction(cluster_id, video_data):
    cluster    = CLUSTERS[cluster_id]
    frames_b64 = video_data.get("frames_b64") or []
    transcript = (video_data.get("transcript") or "")[:1500] or (video_data.get("description") or "")[:500]
    has_vision = len(frames_b64) > 0
    prompt = f"""You are simulating how a real person from this demographic reacts to {"a video — you can see frames from it above" if has_vision else "a YouTube video"}.

PERSONA SEGMENT: {cluster['label']}
Profile: {cluster['description']}
Interests: {', '.join(cluster['interests'])}
Political lean: {cluster['political_lean']}
Platforms they use: {', '.join(cluster['media_platforms'])}

RECENT NEWS THIS PERSON HAS BEEN EXPOSED TO:
{get_cluster_news_context(cluster_id, limit=6)}

VIDEO THEY JUST WATCHED:
Title: {video_data.get('title', '')}
Channel: {video_data.get('channel', '')}
Duration: {video_data.get('duration', 0)} seconds
Description: {(video_data.get('description') or '')[:300]}
Transcript excerpt: {transcript}

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "watch_completion": <0-100, be realistic — most people abandon videos>,
  "engagement_score": <0-100>,
  "sentiment": "<positive|neutral|negative|polarised>",
  "would_share": <true|false>,
  "would_subscribe": <true|false>,
  "simulated_comment": "<a specific, genuine comment this person would leave — 3-5 sentences, in their natural voice, reflecting their actual background and mood. Reference something concrete from the video. Not generic.>",
  "drop_off_point": "<immediate|first_30s|first_minute|halfway|completion>",
  "drop_off_reason": "<exactly why they stopped — or why they stayed — be specific about what held or lost their attention>",
  "reaction_summary": "<5-7 sentences. What emotionally landed, what felt off, how their background shaped their read of this content. Be specific to this demographic — avoid generic statements that could apply to anyone.>",
  "key_resonance": "<the single most powerful thing that connected — reference something specific from the video and explain why it hit for this audience>",
  "key_friction": "<the single biggest turn-off — tone, pacing, topic framing, presenter style, or relevance gap — be specific, or null>",
  "purchase_or_action_intent": "<would this video move them to act — buy, visit, follow, try? Why or why not? Be honest if the answer is no.>",
  "authenticity_read": "<did this feel genuine or produced? What specific signals gave that impression to this audience?>"
}}"""
    result = _call_claude(prompt, frames_b64=frames_b64 if frames_b64 else None)
    result["cluster_id"]    = cluster_id
    result["cluster_label"] = cluster["label"]
    result["cluster_color"] = cluster["color"]
    return result

def generate_nemotron_segment_reaction(segment_name, personas, video_data, color):
    frames_b64 = video_data.get("frames_b64") or []
    sample = random.sample(personas, min(5, len(personas)))
    persona_summaries = "\n".join([
        f"- {p.get('occupation','Unknown')}, {p.get('age','?')}yo {p.get('sex','')} from {p.get('state','')}, "
        f"{p.get('education','')}, {p.get('income_level','')} income. "
        f"Interests: {(p.get('hobbies_and_interests') or '')[:120]}"
        for p in sample
    ])
    transcript = (video_data.get("transcript") or "")[:1500] or (video_data.get("description") or "")[:500]
    prompt = f"""You are simulating how a specific audience segment reacts to a YouTube video.

SEGMENT NAME: {segment_name}
SEGMENT SIZE: {len(personas)} individuals

REPRESENTATIVE INDIVIDUALS FROM THIS SEGMENT:
{persona_summaries}

VIDEO THEY JUST WATCHED:
Title: {video_data.get('title', '')}
Channel: {video_data.get('channel', '')}
Duration: {video_data.get('duration', 0)} seconds
Description: {(video_data.get('description') or '')[:300]}
Transcript excerpt: {transcript}

Based on the specific backgrounds, interests and demographics of these real individuals, simulate how this segment as a whole would react. Consider the diversity within the segment.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "watch_completion": <0-100>,
  "engagement_score": <0-100>,
  "sentiment": "<positive|neutral|negative|polarised>",
  "would_share": <true|false>,
  "would_subscribe": <true|false>,
  "simulated_comment": "<a specific comment one of these individuals would actually leave — 3-5 sentences, in their natural voice, referencing something concrete from the video>",
  "drop_off_point": "<immediate|first_30s|first_minute|halfway|completion>",
  "drop_off_reason": "<why they stopped or stayed — specific to this group>",
  "reaction_summary": "<5-7 sentences on how this specific group of real people reacts. Reference their occupations, ages, locations where relevant. Note where the group agrees and where they diverge.>",
  "key_resonance": "<what specifically connected with these individuals and why — reference the video and their backgrounds>",
  "key_friction": "<what specifically put them off, or null>",
  "segment_diversity_note": "<where do opinions split within this group? Who loved it, who didn't, and why?>",
  "purchase_or_action_intent": "<would this move them to act? Be specific about which individuals might and which wouldn't.>",
  "authenticity_read": "<did this feel real or polished to this group? What signals did they pick up on?>"
}}"""
    result = _call_claude(prompt, frames_b64=frames_b64 if frames_b64 else None)
    result["cluster_id"]    = f"nemotron_{segment_name.lower().replace(' ','_')}"
    result["cluster_label"] = segment_name
    result["cluster_color"] = color
    result["persona_count"] = len(personas)
    return result

def save_analysis(video_data, result):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO analysis_results (youtube_url, video_title, video_channel,
          real_views, real_likes, detected_topics, summary, reactions)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        video_data.get("url",""), video_data.get("title",""),
        video_data.get("channel",""), video_data.get("view_count") or 0,
        video_data.get("like_count") or 0,
        json.dumps(result.get("detected_topics",[])),
        json.dumps(result.get("summary",{})),
        json.dumps(result.get("segment_reactions",[])),
    ))
    conn.commit(); cur.close(); conn.close()

def _aggregate(reactions):
    if not reactions: return {"error": "No reactions generated"}
    avg_watch      = sum(r["watch_completion"] for r in reactions) / len(reactions)
    avg_engagement = sum(r["engagement_score"]  for r in reactions) / len(reactions)
    sc = {}
    for r in reactions:
        sc[r["sentiment"]] = sc.get(r["sentiment"],0)+1
    share_rate = sum(1 for r in reactions if r.get("would_share")) / len(reactions) * 100
    return {
        "avg_watch_completion": round(avg_watch,1),
        "avg_engagement_score": round(avg_engagement,1),
        "dominant_sentiment":   max(sc, key=sc.get),
        "predicted_share_rate": round(share_rate,1),
        "segments_analysed":    len(reactions)
    }

def _video_meta(v):
    return {"title":v.get("title"),"channel":v.get("channel"),"thumbnail":v.get("thumbnail"),
            "duration":v.get("duration"),"url":v.get("url"),"real_views":v.get("view_count"),"real_likes":v.get("like_count")}

def run_full_analysis(video_data, cluster_ids):
    reactions = []
    for cid in cluster_ids:
        try: reactions.append(generate_cluster_reaction(cid, video_data))
        except Exception as e: print(f"Cluster reaction error {cid}: {e}")
    return {"video":_video_meta(video_data),"summary":_aggregate(reactions),"segment_reactions":reactions,"mode":"clusters"}

def run_nemotron_analysis(video_data, nemotron_segments):
    reactions = []
    for i, seg in enumerate(nemotron_segments):
        seg = seg if isinstance(seg, dict) else seg.dict()
        name = seg.get("name", f"Segment {i+1}")
        try:
            # Fetch matching personas from database using segment criteria
            personas = fetch_nemotron_personas(seg, sample_size=10)
            if not personas:
                print(f"No personas matched for segment: {name}")
                continue
            reactions.append(generate_nemotron_segment_reaction(
                name, personas, video_data, COLORS[i % len(COLORS)]
            ))
            write_reaction_memory(name, video_data, reactions[-1])
        except Exception as e:
            print(f"Nemotron reaction error {name}: {e}")
    return {"video":_video_meta(video_data),"summary":_aggregate(reactions),"segment_reactions":reactions,"mode":"nemotron"}

def fetch_nemotron_personas(segment_criteria, sample_size=10):
    """Query Nemotron personas matching segment criteria."""
    conn = get_conn()
    cur  = conn.cursor()

    conditions = ["age >= %s", "age <= %s"]
    params     = [
        segment_criteria.get("age_min", 18),
        segment_criteria.get("age_max", 99)
    ]

    if segment_criteria.get("sex"):
        conditions.append("LOWER(sex) = LOWER(%s)")
        params.append(segment_criteria["sex"])

    if segment_criteria.get("state"):
        conditions.append("LOWER(state) = LOWER(%s)")
        params.append(segment_criteria["state"])

    if segment_criteria.get("education"):
        conditions.append("LOWER(education) ILIKE %s")
        params.append(f"%{segment_criteria['education'].lower()}%")

    if segment_criteria.get("income_level"):
        conditions.append("LOWER(income_level) ILIKE %s")
        params.append(f"%{segment_criteria['income_level'].lower()}%")

    if segment_criteria.get("occupation_keywords"):
        keywords = [k.strip() for k in segment_criteria["occupation_keywords"].split(",")]
        occ = " OR ".join(["LOWER(occupation) ILIKE %s"] * len(keywords))
        conditions.append(f"({occ})")
        params.extend([f"%{k.lower()}%" for k in keywords])

    if segment_criteria.get("interest_keywords"):
        keywords = [k.strip() for k in segment_criteria["interest_keywords"].split(",")]
        ints = " OR ".join(["LOWER(hobbies_and_interests) ILIKE %s"] * len(keywords))
        conditions.append(f"({ints})")
        params.extend([f"%{k.lower()}%" for k in keywords])

    if segment_criteria.get("political_affiliation"):
        conditions.append("LOWER(political_affiliation) ILIKE %s")
        params.append(f"%{segment_criteria['political_affiliation'].lower()}%")

    where = " AND ".join(conditions)
    cur.execute(f"""
        SELECT age, sex, state, city, education, occupation,
               income_level, political_affiliation,
               hobbies_and_interests, skills_and_expertise, persona
        FROM nemotron_personas
        WHERE {where}
        ORDER BY RANDOM()
        LIMIT %s
    """, params + [sample_size])

    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def generate_nemotron_reaction(segment_name: str, personas: list, video_data: dict) -> dict:
    """Generate reaction using real Nemotron personas as context."""
    if not personas:
        return {
            "cluster_id":    segment_name,
            "cluster_label": segment_name,
            "cluster_color": "#888780",
            "watch_completion": 50, "engagement_score": 30,
            "sentiment": "neutral", "would_share": False,
            "would_subscribe": False,
            "simulated_comment": "Insufficient personas to simulate.",
            "drop_off_point": "halfway",
            "reaction_summary": "No matching personas found.",
            "key_resonance": None, "key_friction": None,
            "persona_count": 0
        }

    persona_sketches = "\n".join([
        f"- {p.get('age','?')}yo {p.get('sex','')} {p.get('occupation','unknown occupation')} "
        f"from {p.get('state','?')}, {p.get('income_level','')} income, "
        f"interests: {(p.get('hobbies_and_interests') or '')[:100]}"
        for p in personas[:8]
    ])

    transcript = (video_data.get("transcript") or "")[:1500] or (video_data.get("description") or "")[:500]

    prompt = f"""You are simulating how a specific group of real people react to a YouTube video.

SEGMENT NAME: {segment_name}
ACTUAL INDIVIDUALS IN THIS SEGMENT ({len(personas)} people):
{persona_sketches}

VIDEO THEY JUST WATCHED:
Title: {video_data.get('title', '')}
Channel: {video_data.get('channel', '')}
Duration: {video_data.get('duration', 0)} seconds
Description: {(video_data.get('description') or '')[:300]}
Transcript excerpt: {transcript}

React as this group of real individuals — not a stereotype. Consider how their specific backgrounds, occupations, income levels and interests would shape their genuine reaction. Note any meaningful disagreement within the group.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "watch_completion": <0-100>,
  "engagement_score": <0-100>,
  "sentiment": "<positive|neutral|negative|polarised>",
  "would_share": <true|false>,
  "would_subscribe": <true|false>,
  "simulated_comment": "<a comment one of these individuals would actually leave, in their natural voice>",
  "drop_off_point": "<immediate|first_30s|first_minute|halfway|completion>",
  "reaction_summary": "<2-3 sentences capturing the group's genuine collective reaction>",
  "key_resonance": "<what connected most with this specific group, or null>",
  "key_friction": "<what put them off most, or null>",
  "segment_diversity_note": "<any notable split within the group, or null>"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
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
            "key_resonance": None, "key_friction": None,
            "segment_diversity_note": None
        }

    result["cluster_id"]    = segment_name
    result["cluster_label"] = segment_name
    result["cluster_color"] = "#5856D6"
    result["persona_count"] = len(personas)
    return result

def write_reaction_memory(segment_name: str, video_data: dict, reaction: dict):
    """Write analysis reaction back as a persona memory for future context."""
    try:
        from datetime import datetime
        conn = get_conn()
        cur  = conn.cursor()
        memory_text = (
            f"Reacted to a video titled '{video_data.get('title','')}' "
            f"by '{video_data.get('channel','')}'. "
            f"Sentiment: {reaction.get('sentiment','unknown')}. "
            f"Watch completion: {reaction.get('watch_completion',0)}%. "
            f"Key resonance: {reaction.get('key_resonance') or 'none'}. "
            f"Key friction: {reaction.get('key_friction') or 'none'}."
        )
        cur.execute("""
            INSERT INTO persona_memories (cluster_id, memory_text, topic, headline, memory_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            segment_name,
            memory_text,
            "video_reaction",
            video_data.get('title','')[:200],
            datetime.now().strftime("%Y-%m-%d")
        ))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Memory write-back error: {e}")

def run_nemotron_analysis(video_data: dict, nemotron_segments: list) -> dict:
    """Run analysis using Nemotron persona segments."""
    reactions = []

    for seg in nemotron_segments:
        criteria = seg if isinstance(seg, dict) else seg.dict()
        name     = criteria.get("name", "Unnamed segment")
        try:
            personas = fetch_nemotron_personas(criteria, sample_size=10)
            reaction = generate_nemotron_reaction(name, personas, video_data)
            reactions.append(reaction)
            write_reaction_memory(name, video_data, reaction)
        except Exception as e:
            print(f"Nemotron reaction error for {name}: {e}")

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
