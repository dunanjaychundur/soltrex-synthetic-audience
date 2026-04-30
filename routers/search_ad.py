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

def build_ad_preview(req: SearchAdRequest) -> str:
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
        result = {
            "creative_scores": {"relevance": 5, "headline_strength": 5, "description_quality": 5, "url_clarity": 5, "overall_quality": 5},
            "creative_feedback": {"strongest_element": "N/A", "weakest_element": "N/A", "headline_critique": "N/A", "description_critique": "N/A", "improvement_suggestion": "N/A"},
            "audience_reaction": {"would_click": False, "click_likelihood": 30, "relevance_to_segment": 5, "trust_score": 5, "emotional_response": "neutral", "click_reason": "N/A", "objection": None},
            "performance_estimate": {"predicted_ctr_multiplier": 1.0, "predicted_ctr": benchmark["avg_ctr"], "confidence": "low"}
        }

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
        personas = fetch_nemotron_personas({"age_min": segment.get("age_min",18), "age_max": segment.get("age_max",99)}, sample_size=8)

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
        result = {
            "creative_scores": {"relevance": 5, "headline_strength": 5, "description_quality": 5, "url_clarity": 5, "overall_quality": 5},
            "creative_feedback": {"strongest_element": "N/A", "weakest_element": "N/A", "headline_critique": "N/A", "description_critique": "N/A", "improvement_suggestion": "N/A"},
            "audience_reaction": {"would_click": False, "click_likelihood": 30, "relevance_to_segment": 5, "trust_score": 5, "emotional_response": "neutral", "click_reason": "N/A", "objection": None},
            "performance_estimate": {"predicted_ctr_multiplier": 1.0, "predicted_ctr": benchmark["avg_ctr"], "confidence": "low"}
        }

    result["cluster_id"]    = f"nemotron_{name.lower().replace(' ','_')}"
    result["cluster_label"] = name
    result["cluster_color"] = "#EE205D"
    result["benchmark_ctr"] = benchmark["avg_ctr"]
    result["persona_count"] = len(personas)
    return result

def aggregate_scores(results: list, req: SearchAdRequest, benchmark: dict) -> dict:
    if not results:
        return {}

    avg_quality    = sum(r["creative_scores"]["overall_quality"] for r in results) / len(results)
    avg_click_like = sum(r["audience_reaction"]["click_likelihood"] for r in results) / len(results)
    avg_ctr        = sum(r["performance_estimate"]["predicted_ctr"] for r in results) / len(results)
    avg_relevance  = sum(r["audience_reaction"]["relevance_to_segment"] for r in results) / len(results)

    impressions    = req.monthly_impressions or 10000
    est_clicks     = int(impressions * avg_ctr / 100)

    return {
        "avg_creative_quality": round(avg_quality, 1),
        "avg_click_likelihood": round(avg_click_like, 1),
        "avg_predicted_ctr":    round(avg_ctr, 2),
        "benchmark_ctr":        benchmark["avg_ctr"],
        "ctr_vs_benchmark":     round(avg_ctr - benchmark["avg_ctr"], 2),
        "estimated_monthly_clicks": est_clicks,
        "monthly_impressions":  impressions,
        "avg_segment_relevance": round(avg_relevance, 1),
        "segments_scored":      len(results),
    }

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
        "summary":          aggregate_scores(results, req, benchmark),
        "segment_scores":   results,
        "benchmark":        benchmark,
    }
