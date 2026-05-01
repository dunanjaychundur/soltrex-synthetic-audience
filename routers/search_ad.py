from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import anthropic
import json
import re
from services.persona_store import CLUSTERS
from services.news_service import get_cluster_news_context
from services.reaction_engine import fetch_nemotron_personas

router = APIRouter()
client = anthropic.Anthropic()

INDUSTRY_BENCHMARKS = {
    "default":          {"avg_ctr": 3.17, "avg_cpc": 2.69},
    "ecommerce":        {"avg_ctr": 2.69, "avg_cpc": 1.16},
    "finance":          {"avg_ctr": 2.91, "avg_cpc": 3.44},
    "health":           {"avg_ctr": 3.27, "avg_cpc": 2.62},
    "travel":           {"avg_ctr": 4.68, "avg_cpc": 1.53},
    "b2b":              {"avg_ctr": 2.55, "avg_cpc": 3.33},
    "technology":       {"avg_ctr": 2.09, "avg_cpc": 3.80},
    "retail":           {"avg_ctr": 2.69, "avg_cpc": 1.16},
    "automotive":       {"avg_ctr": 4.00, "avg_cpc": 2.46},
    "real_estate":      {"avg_ctr": 3.71, "avg_cpc": 2.37},
    "food_beverage":    {"avg_ctr": 3.78, "avg_cpc": 1.44},
    "entertainment":    {"avg_ctr": 4.07, "avg_cpc": 1.93},
}


class SearchAdRequest(BaseModel):
    headline_1:          str
    headline_2:          Optional[str] = ""
    headline_3:          Optional[str] = ""
    description_1:       str
    description_2:       Optional[str] = ""
    display_url:         Optional[str] = ""
    target_keyword:      str
    industry:            Optional[str] = "default"
    monthly_impressions: Optional[int] = 10000
    cluster_ids:         Optional[list[str]] = None
    nemotron_segments:   Optional[list[dict]] = None
    mode:                Optional[str] = "clusters"


class JourneyRequest(BaseModel):
    """Search ad + landing page images for full funnel scoring."""
    headline_1:          str
    headline_2:          Optional[str] = ""
    headline_3:          Optional[str] = ""
    description_1:       str
    description_2:       Optional[str] = ""
    display_url:         Optional[str] = ""
    target_keyword:      str
    industry:            Optional[str] = "default"
    monthly_impressions: Optional[int] = 10000
    # Landing page: list of base64-encoded images (JPEGs/PNGs or PDF pages rasterised client-side)
    landing_page_images: list[str]
    # Optional label so Claude knows what action to evaluate conversion against
    conversion_goal:     Optional[str] = "complete the primary call to action"
    cluster_ids:         Optional[list[str]] = None
    nemotron_segments:   Optional[list[dict]] = None
    mode:                Optional[str] = "clusters"


def build_ad_preview(req) -> str:
    h1 = req.headline_1
    h2 = req.headline_2 or ""
    h3 = req.headline_3 or ""
    headlines = " | ".join(filter(None, [h1, h2, h3]))
    return f"""
AD PREVIEW:
URL: {req.display_url or 'www.example.com'}
Headlines: {headlines}
Description: {req.description_1}{(' ' + req.description_2) if req.description_2 else ''}
Target keyword: [{req.target_keyword}]
"""


# ---------------------------------------------------------------------------
# Original ad-only scoring (unchanged)
# ---------------------------------------------------------------------------

def score_ad_for_cluster(cluster_id: str, req: SearchAdRequest, ad_preview: str) -> dict:
    cluster      = CLUSTERS[cluster_id]
    news_context = get_cluster_news_context(cluster_id, limit=4)
    benchmark    = INDUSTRY_BENCHMARKS.get(req.industry or "default", INDUSTRY_BENCHMARKS["default"])

    prompt = f"""You are a search marketing expert AND a member of this audience segment evaluating a Google search ad.

AUDIENCE SEGMENT: {cluster['label']}
Profile: {cluster['description']}
Interests: {', '.join(cluster['interests'])}
Political lean: {cluster['political_lean']}

RECENT CONTEXT THIS AUDIENCE HAS BEEN EXPOSED TO:
{news_context}

SEARCH AD BEING EVALUATED:
{ad_preview}

Evaluate this ad from two perspectives:

1. As a CREATIVE DIRECTOR: Score the ad's technical quality
2. As a MEMBER OF THIS AUDIENCE: Would this ad make you click?

Industry benchmark CTR: {benchmark['avg_ctr']}%

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "creative_scores": {{
    "relevance":        <0-10, how well headlines match the keyword intent>,
    "headline_strength":<0-10, are headlines compelling, specific, benefit-driven?>,
    "description_quality":<0-10, does it expand value prop, include CTA?>,
    "url_clarity":      <0-10, is the display URL clean and trustworthy?>,
    "overall_quality":  <0-10, holistic creative score>
  }},
  "creative_feedback": {{
    "strongest_element": "<what works best about this ad>",
    "weakest_element":   "<the single biggest creative weakness>",
    "headline_critique": "<specific feedback on headlines — are they benefit-driven, specific, emotionally resonant?>",
    "description_critique": "<specific feedback on description copy>",
    "improvement_suggestion": "<one concrete rewrite suggestion for the weakest element>"
  }},
  "audience_reaction": {{
    "would_click": <true|false>,
    "click_likelihood": <0-100, likelihood this segment clicks>,
    "relevance_to_segment": <0-10, how relevant is this ad to this specific audience's needs/interests>,
    "trust_score": <0-10, does this ad feel credible to this audience>,
    "emotional_response": "<positive|neutral|negative|suspicious>",
    "click_reason": "<why they would or wouldn't click — be specific to this segment's psychology>",
    "objection": "<what would make them hesitate or not click, or null>"
  }},
  "performance_estimate": {{
    "predicted_ctr_multiplier": <0.5-3.0, multiplier vs industry benchmark based on creative quality and segment fit>,
    "predicted_ctr":            <calculated: benchmark_ctr * multiplier, rounded to 2 decimals>,
    "confidence":               "<low|medium|high>"
  }}
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = _fallback_ad_score(benchmark)

    result["cluster_id"]    = cluster_id
    result["cluster_label"] = cluster["label"]
    result["cluster_color"] = cluster["color"]
    result["benchmark_ctr"] = benchmark["avg_ctr"]
    return result


def score_ad_for_nemotron(segment: dict, req: SearchAdRequest, ad_preview: str) -> dict:
    name      = segment.get("name", "Segment")
    personas  = fetch_nemotron_personas(segment, sample_size=8)
    benchmark = INDUSTRY_BENCHMARKS.get(req.industry or "default", INDUSTRY_BENCHMARKS["default"])

    if not personas:
        personas = fetch_nemotron_personas({"age_min": segment.get("age_min", 18), "age_max": segment.get("age_max", 99)}, sample_size=8)

    persona_sketches = "\n".join([
        f"- {p.get('age','?')}yo {p.get('sex','')} {p.get('occupation','').replace('_',' ')} from {p.get('state','')}, {p.get('education','').replace('_',' ')} education. Interests: {(p.get('hobbies_and_interests') or '')[:100]}"
        for p in personas[:6]
    ])

    prompt = f"""You are a search marketing expert evaluating a Google search ad on behalf of a specific audience segment.

SEGMENT: {name}
REPRESENTATIVE INDIVIDUALS:
{persona_sketches}

SEARCH AD:
{ad_preview}

Industry benchmark CTR: {benchmark['avg_ctr']}%

Score this ad from both a creative quality perspective and from the perspective of these specific individuals.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "creative_scores": {{
    "relevance":             <0-10>,
    "headline_strength":     <0-10>,
    "description_quality":   <0-10>,
    "url_clarity":           <0-10>,
    "overall_quality":       <0-10>
  }},
  "creative_feedback": {{
    "strongest_element":      "<what works best>",
    "weakest_element":        "<biggest weakness>",
    "headline_critique":      "<specific headline feedback>",
    "description_critique":   "<specific description feedback>",
    "improvement_suggestion": "<one concrete rewrite suggestion>"
  }},
  "audience_reaction": {{
    "would_click":            <true|false>,
    "click_likelihood":       <0-100>,
    "relevance_to_segment":   <0-10>,
    "trust_score":            <0-10>,
    "emotional_response":     "<positive|neutral|negative|suspicious>",
    "click_reason":           "<why they would or wouldn't — specific to these individuals>",
    "objection":              "<what would stop them, or null>"
  }},
  "performance_estimate": {{
    "predicted_ctr_multiplier": <0.5-3.0>,
    "predicted_ctr":            <benchmark * multiplier, 2 decimals>,
    "confidence":               "<low|medium|high>"
  }}
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = _fallback_ad_score(benchmark)

    result["cluster_id"]    = f"nemotron_{name.lower().replace(' ','_')}"
    result["cluster_label"] = name
    result["cluster_color"] = "#EE205D"
    result["benchmark_ctr"] = benchmark["avg_ctr"]
    result["persona_count"] = len(personas)
    return result


# ---------------------------------------------------------------------------
# Full journey scoring (ad + landing page)
# ---------------------------------------------------------------------------

def _build_vision_content(images_b64: list, media_type: str = "image/jpeg") -> list:
    """Convert base64 image list into Claude multimodal content blocks."""
    blocks = []
    for b64 in images_b64[:6]:  # cap at 6 images
        if b64 and len(b64) > 100:
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64}
            })
    return blocks


def score_journey_for_cluster(cluster_id: str, req: JourneyRequest, ad_preview: str) -> dict:
    cluster      = CLUSTERS[cluster_id]
    news_context = get_cluster_news_context(cluster_id, limit=4)
    benchmark    = INDUSTRY_BENCHMARKS.get(req.industry or "default", INDUSTRY_BENCHMARKS["default"])
    n_pages      = len(req.landing_page_images)

    # Build multimodal content: landing page images first, then the prompt
    image_blocks = _build_vision_content(req.landing_page_images)

    prompt_text = f"""You are evaluating the FULL customer journey for a Google search ad — from the moment the user sees the ad in search results through to a final conversion decision on the landing page.

AUDIENCE SEGMENT: {cluster['label']}
Profile: {cluster['description']}
Interests: {', '.join(cluster['interests'])}
Political lean: {cluster['political_lean']}

RECENT CONTEXT THIS AUDIENCE HAS BEEN EXPOSED TO:
{news_context}

---
STEP 1 — SEARCH AD (what they see before clicking):
{ad_preview}

---
STEP 2 — LANDING PAGE (the {n_pages} image(s) above show what they land on after clicking):
You can see the landing page above. Evaluate what this audience sees scroll by scroll.

CONVERSION GOAL: {req.conversion_goal}
INDUSTRY BENCHMARK CTR: {benchmark['avg_ctr']}%

---
Evaluate the entire journey as this audience member would experience it. Be specific — reference what you actually see in the landing page images.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "ad_stage": {{
    "creative_scores": {{
      "relevance":          <0-10>,
      "headline_strength":  <0-10>,
      "description_quality":<0-10>,
      "url_clarity":        <0-10>,
      "overall_quality":    <0-10>
    }},
    "would_click":          <true|false>,
    "click_likelihood":     <0-100>,
    "emotional_response":   "<positive|neutral|negative|suspicious>",
    "click_reason":         "<why they would or wouldn't click>",
    "predicted_ctr":        <benchmark * quality multiplier, 2 decimals>
  }},
  "landing_page_stage": {{
    "first_impression":     "<their immediate gut reaction in 1-2 sentences — what hits them visually and what promise is set>",
    "promise_match":        <0-10, how well does the landing page deliver on what the ad promised?>,
    "visual_appeal":        <0-10, design quality, clarity, professionalism as this audience perceives it>,
    "message_clarity":      <0-10, is the value proposition clear and immediately understandable?>,
    "trust_signals":        <0-10, do they see social proof, credibility markers, or security signals they trust?>,
    "scroll_behaviour":     "<immediate_exit|skims_hero|reads_to_cta|reads_fully — how far does this segment realistically scroll?>",
    "drop_off_section":     "<which section they abandon and why, or null if they reach the CTA>",
    "friction_points":      "<specific elements — copy, design, missing info — that give this audience pause>",
    "what_works":           "<what on the landing page specifically resonates with this audience>"
  }},
  "conversion_stage": {{
    "would_convert":        <true|false>,
    "conversion_likelihood":<0-100>,
    "conversion_blocker":   "<the single biggest reason they wouldn't convert, or null>",
    "conversion_motivator": "<the strongest thing pushing them toward conversion>",
    "trust_score":          <0-10, overall trust in the brand/offer after seeing the full journey>
  }},
  "funnel_verdict": {{
    "weakest_stage":        "<ad|landing_page|conversion — where does the funnel lose this segment?>",
    "biggest_fix":          "<the single highest-impact change to improve conversion for this segment>",
    "journey_coherence":    <0-10, how seamlessly does the ad promise flow into the landing page experience?>,
    "overall_funnel_score": <0-10>
  }}
}}"""

    content = image_blocks + [{"type": "text", "text": prompt_text}]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = _fallback_journey_score(benchmark)

    result["cluster_id"]    = cluster_id
    result["cluster_label"] = cluster["label"]
    result["cluster_color"] = cluster["color"]
    result["benchmark_ctr"] = benchmark["avg_ctr"]
    return result


def score_journey_for_nemotron(segment: dict, req: JourneyRequest, ad_preview: str) -> dict:
    name      = segment.get("name", "Segment")
    personas  = fetch_nemotron_personas(segment, sample_size=8)
    benchmark = INDUSTRY_BENCHMARKS.get(req.industry or "default", INDUSTRY_BENCHMARKS["default"])
    n_pages   = len(req.landing_page_images)

    if not personas:
        personas = fetch_nemotron_personas({"age_min": segment.get("age_min", 18), "age_max": segment.get("age_max", 99)}, sample_size=8)

    persona_sketches = "\n".join([
        f"- {p.get('age','?')}yo {p.get('sex','')} {p.get('occupation','').replace('_',' ')} from {p.get('state','')}, {p.get('education','').replace('_',' ')} education. Interests: {(p.get('hobbies_and_interests') or '')[:100]}"
        for p in personas[:6]
    ])

    image_blocks = _build_vision_content(req.landing_page_images)

    prompt_text = f"""You are evaluating the FULL customer journey for a Google search ad on behalf of a specific audience segment.

SEGMENT: {name}
REPRESENTATIVE INDIVIDUALS:
{persona_sketches}

---
STEP 1 — SEARCH AD:
{ad_preview}

---
STEP 2 — LANDING PAGE ({n_pages} image(s) shown above):
CONVERSION GOAL: {req.conversion_goal}
INDUSTRY BENCHMARK CTR: {benchmark['avg_ctr']}%

---
Evaluate the entire journey as these specific individuals would experience it.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "ad_stage": {{
    "creative_scores": {{
      "relevance":          <0-10>,
      "headline_strength":  <0-10>,
      "description_quality":<0-10>,
      "url_clarity":        <0-10>,
      "overall_quality":    <0-10>
    }},
    "would_click":          <true|false>,
    "click_likelihood":     <0-100>,
    "emotional_response":   "<positive|neutral|negative|suspicious>",
    "click_reason":         "<why they would or wouldn't click>",
    "predicted_ctr":        <benchmark * quality multiplier, 2 decimals>
  }},
  "landing_page_stage": {{
    "first_impression":     "<their immediate gut reaction — what hits them visually and what promise is set>",
    "promise_match":        <0-10>,
    "visual_appeal":        <0-10>,
    "message_clarity":      <0-10>,
    "trust_signals":        <0-10>,
    "scroll_behaviour":     "<immediate_exit|skims_hero|reads_to_cta|reads_fully>",
    "drop_off_section":     "<section they abandon and why, or null>",
    "friction_points":      "<specific elements that give this audience pause>",
    "what_works":           "<what resonates with this audience>"
  }},
  "conversion_stage": {{
    "would_convert":        <true|false>,
    "conversion_likelihood":<0-100>,
    "conversion_blocker":   "<biggest reason they wouldn't convert, or null>",
    "conversion_motivator": "<strongest thing pushing them toward conversion>",
    "trust_score":          <0-10>
  }},
  "funnel_verdict": {{
    "weakest_stage":        "<ad|landing_page|conversion>",
    "biggest_fix":          "<single highest-impact change for this segment>",
    "journey_coherence":    <0-10>,
    "overall_funnel_score": <0-10>
  }}
}}"""

    content = image_blocks + [{"type": "text", "text": prompt_text}]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = _fallback_journey_score(benchmark)

    result["cluster_id"]    = f"nemotron_{name.lower().replace(' ','_')}"
    result["cluster_label"] = name
    result["cluster_color"] = "#EE205D"
    result["benchmark_ctr"] = benchmark["avg_ctr"]
    result["persona_count"] = len(personas)
    return result


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def aggregate_scores(results: list, req, benchmark: dict) -> dict:
    if not results:
        return {}

    avg_quality    = sum(r["creative_scores"]["overall_quality"] for r in results) / len(results)
    avg_click_like = sum(r["audience_reaction"]["click_likelihood"] for r in results) / len(results)
    avg_ctr        = sum(r["performance_estimate"]["predicted_ctr"] for r in results) / len(results)
    avg_relevance  = sum(r["audience_reaction"]["relevance_to_segment"] for r in results) / len(results)

    impressions = req.monthly_impressions or 10000
    est_clicks  = int(impressions * avg_ctr / 100)

    return {
        "avg_creative_quality":     round(avg_quality, 1),
        "avg_click_likelihood":     round(avg_click_like, 1),
        "avg_predicted_ctr":        round(avg_ctr, 2),
        "benchmark_ctr":            benchmark["avg_ctr"],
        "ctr_vs_benchmark":         round(avg_ctr - benchmark["avg_ctr"], 2),
        "estimated_monthly_clicks": est_clicks,
        "monthly_impressions":      impressions,
        "avg_segment_relevance":    round(avg_relevance, 1),
        "segments_scored":          len(results),
    }


def aggregate_journey_scores(results: list, req: JourneyRequest, benchmark: dict) -> dict:
    if not results:
        return {}

    def safe_avg(key_path):
        vals = []
        for r in results:
            obj = r
            for k in key_path:
                obj = obj.get(k, {}) if isinstance(obj, dict) else None
                if obj is None:
                    break
            if isinstance(obj, (int, float)):
                vals.append(obj)
        return round(sum(vals) / len(vals), 1) if vals else 0

    avg_ctr         = safe_avg(["ad_stage", "predicted_ctr"])
    avg_click       = safe_avg(["ad_stage", "click_likelihood"])
    avg_lp_score    = safe_avg(["landing_page_stage", "promise_match"])
    avg_conversion  = safe_avg(["conversion_stage", "conversion_likelihood"])
    avg_funnel      = safe_avg(["funnel_verdict", "overall_funnel_score"])
    avg_coherence   = safe_avg(["funnel_verdict", "journey_coherence"])

    impressions = req.monthly_impressions or 10000
    est_clicks  = int(impressions * avg_ctr / 100)
    est_conv    = int(est_clicks * avg_conversion / 100)

    weakest_stages = [r.get("funnel_verdict", {}).get("weakest_stage") for r in results if r.get("funnel_verdict")]
    weakest_counts = {}
    for s in weakest_stages:
        if s:
            weakest_counts[s] = weakest_counts.get(s, 0) + 1
    most_common_weak = max(weakest_counts, key=weakest_counts.get) if weakest_counts else "unknown"

    return {
        "avg_predicted_ctr":          round(avg_ctr, 2),
        "benchmark_ctr":              benchmark["avg_ctr"],
        "ctr_vs_benchmark":           round(avg_ctr - benchmark["avg_ctr"], 2),
        "avg_click_likelihood":       round(avg_click, 1),
        "avg_landing_page_score":     round(avg_lp_score, 1),
        "avg_conversion_likelihood":  round(avg_conversion, 1),
        "avg_funnel_score":           round(avg_funnel, 1),
        "avg_journey_coherence":      round(avg_coherence, 1),
        "estimated_monthly_clicks":   est_clicks,
        "estimated_monthly_converts": est_conv,
        "monthly_impressions":        impressions,
        "segments_scored":            len(results),
        "most_common_weak_stage":     most_common_weak,
    }


# ---------------------------------------------------------------------------
# Fallback objects
# ---------------------------------------------------------------------------

def _fallback_ad_score(benchmark):
    return {
        "creative_scores":  {"relevance": 5, "headline_strength": 5, "description_quality": 5, "url_clarity": 5, "overall_quality": 5},
        "creative_feedback":{"strongest_element": "N/A", "weakest_element": "N/A", "headline_critique": "N/A", "description_critique": "N/A", "improvement_suggestion": "N/A"},
        "audience_reaction":{"would_click": False, "click_likelihood": 30, "relevance_to_segment": 5, "trust_score": 5, "emotional_response": "neutral", "click_reason": "N/A", "objection": None},
        "performance_estimate": {"predicted_ctr_multiplier": 1.0, "predicted_ctr": benchmark["avg_ctr"], "confidence": "low"}
    }


def _fallback_journey_score(benchmark):
    return {
        "ad_stage": {
            "creative_scores": {"relevance": 5, "headline_strength": 5, "description_quality": 5, "url_clarity": 5, "overall_quality": 5},
            "would_click": False, "click_likelihood": 30, "emotional_response": "neutral",
            "click_reason": "N/A", "predicted_ctr": benchmark["avg_ctr"]
        },
        "landing_page_stage": {
            "first_impression": "N/A", "promise_match": 5, "visual_appeal": 5,
            "message_clarity": 5, "trust_signals": 5, "scroll_behaviour": "skims_hero",
            "drop_off_section": None, "friction_points": "N/A", "what_works": "N/A"
        },
        "conversion_stage": {
            "would_convert": False, "conversion_likelihood": 20,
            "conversion_blocker": "N/A", "conversion_motivator": "N/A", "trust_score": 5
        },
        "funnel_verdict": {
            "weakest_stage": "unknown", "biggest_fix": "N/A",
            "journey_coherence": 5, "overall_funnel_score": 5
        }
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/score")
def score_search_ad(req: SearchAdRequest):
    ad_preview = build_ad_preview(req)
    benchmark  = INDUSTRY_BENCHMARKS.get(req.industry or "default", INDUSTRY_BENCHMARKS["default"])
    results    = []

    if req.mode == "nemotron" and req.nemotron_segments:
        for seg in req.nemotron_segments:
            try:
                results.append(score_ad_for_nemotron(seg, req, ad_preview))
            except Exception as e:
                print(f"Search score error for {seg.get('name')}: {e}")
    else:
        cluster_ids = req.cluster_ids or list(CLUSTERS.keys())
        for cluster_id in cluster_ids:
            try:
                results.append(score_ad_for_cluster(cluster_id, req, ad_preview))
            except Exception as e:
                print(f"Search score error for {cluster_id}: {e}")

    return {
        "ad": {
            "headline_1":     req.headline_1,
            "headline_2":     req.headline_2,
            "headline_3":     req.headline_3,
            "description_1":  req.description_1,
            "description_2":  req.description_2,
            "display_url":    req.display_url,
            "target_keyword": req.target_keyword,
            "industry":       req.industry,
        },
        "summary":        aggregate_scores(results, req, benchmark),
        "segment_scores": results,
        "benchmark":      benchmark,
    }


@router.post("/score-journey")
def score_customer_journey(req: JourneyRequest):
    """Score the full customer journey: search ad click intent + landing page reaction + conversion."""
    if not req.landing_page_images:
        return {"error": "No landing page images provided."}

    ad_preview = build_ad_preview(req)
    benchmark  = INDUSTRY_BENCHMARKS.get(req.industry or "default", INDUSTRY_BENCHMARKS["default"])
    results    = []

    if req.mode == "nemotron" and req.nemotron_segments:
        for seg in req.nemotron_segments:
            try:
                results.append(score_journey_for_nemotron(seg, req, ad_preview))
            except Exception as e:
                print(f"Journey score error for {seg.get('name')}: {e}")
    else:
        cluster_ids = req.cluster_ids or list(CLUSTERS.keys())
        for cluster_id in cluster_ids:
            try:
                results.append(score_journey_for_cluster(cluster_id, req, ad_preview))
            except Exception as e:
                print(f"Journey score error for {cluster_id}: {e}")

    return {
        "mode": "journey",
        "ad": {
            "headline_1":     req.headline_1,
            "headline_2":     req.headline_2,
            "headline_3":     req.headline_3,
            "description_1":  req.description_1,
            "description_2":  req.description_2,
            "display_url":    req.display_url,
            "target_keyword": req.target_keyword,
            "industry":       req.industry,
        },
        "landing_page_count": len(req.landing_page_images),
        "conversion_goal":    req.conversion_goal,
        "summary":            aggregate_journey_scores(results, req, benchmark),
        "segment_scores":     results,
        "benchmark":          benchmark,
    }
