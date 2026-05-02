from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import anthropic
import json
import re
import os
import tempfile
from services.persona_store import CLUSTERS
from services.news_service import get_cluster_news_context
from services.reaction_engine import fetch_nemotron_personas
from services.landing_page_service import process_landing_page_file

router = APIRouter()
client = anthropic.Anthropic()

INDUSTRY_BENCHMARKS = {
    "default":       {"avg_ctr": 3.17, "avg_cpc": 2.69, "avg_cvr": 3.75},
    "ecommerce":     {"avg_ctr": 2.69, "avg_cpc": 1.16, "avg_cvr": 2.81},
    "finance":       {"avg_ctr": 2.91, "avg_cpc": 3.44, "avg_cvr": 5.10},
    "health":        {"avg_ctr": 3.27, "avg_cpc": 2.62, "avg_cvr": 3.36},
    "travel":        {"avg_ctr": 4.68, "avg_cpc": 1.53, "avg_cvr": 3.55},
    "b2b":           {"avg_ctr": 2.55, "avg_cpc": 3.33, "avg_cvr": 2.23},
    "technology":    {"avg_ctr": 2.09, "avg_cpc": 3.80, "avg_cvr": 2.92},
    "retail":        {"avg_ctr": 2.69, "avg_cpc": 1.16, "avg_cvr": 2.81},
    "automotive":    {"avg_ctr": 4.00, "avg_cpc": 2.46, "avg_cvr": 6.03},
    "real_estate":   {"avg_ctr": 3.71, "avg_cpc": 2.37, "avg_cvr": 2.47},
    "food_beverage": {"avg_ctr": 3.78, "avg_cpc": 1.44, "avg_cvr": 3.58},
    "entertainment": {"avg_ctr": 4.07, "avg_cpc": 1.93, "avg_cvr": 3.09},
}

def build_ad_text(headline_1, headline_2, headline_3, description_1, description_2, display_url, target_keyword):
    headlines = " | ".join(filter(None, [headline_1, headline_2, headline_3]))
    desc      = " ".join(filter(None, [description_1, description_2]))
    return f"""SEARCH AD:
URL: {display_url or 'www.example.com'}
Headlines: {headlines}
Description: {desc}
Target keyword: [{target_keyword}]"""

def build_vision_content(frames: list, text: str) -> list:
    """Build Claude multimodal message content with images + text."""
    content = []
    for f in frames[:8]:
        if f.get("data") and len(f["data"]) > 100:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": f["media_type"], "data": f["data"]}
            })
    content.append({"type": "text", "text": text})
    return content

def score_journey_for_cluster(
    cluster_id: str,
    ad_text: str,
    lp_frames: list,
    conversion_action: str,
    industry: str,
    benchmark: dict,
    news_context: str
) -> dict:
    cluster = CLUSTERS[cluster_id]
    has_lp  = len(lp_frames) > 0

    lp_instruction = f"""
LANDING PAGE: {len(lp_frames)} screenshot(s)/pages provided above showing the landing page the ad leads to.
CONVERSION ACTION: {conversion_action}
""" if has_lp else "\nLANDING PAGE: Not provided — score ad only.\n"

    prompt = f"""You are simultaneously a search marketing expert AND a member of this audience segment evaluating a complete customer journey.

AUDIENCE SEGMENT: {cluster['label']}
Profile: {cluster['description']}
Interests: {', '.join(cluster['interests'])}
Political lean: {cluster['political_lean']}

RECENT NEWS CONTEXT FOR THIS AUDIENCE:
{news_context}

{ad_text}
{lp_instruction}

Evaluate the COMPLETE customer journey — from seeing the ad to arriving on the landing page to deciding whether to convert.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "ad_stage": {{
    "would_click": <true|false>,
    "click_likelihood": <0-100>,
    "headline_strength": <0-10>,
    "relevance_to_segment": <0-10>,
    "emotional_response": "<positive|neutral|negative|suspicious>",
    "click_reasoning": "<why this segment would or wouldn't click — specific to their psychology>",
    "predicted_ctr_multiplier": <0.5-3.0 vs industry benchmark>
  }},
  "landing_page_stage": {json.dumps({
    "first_impression": "<what hits them in the first 3 seconds>",
    "promise_match": "<0-10, does the page deliver on the ad's promise?>",
    "trust_signals": "<0-10, credibility, social proof, professionalism>",
    "clarity": "<0-10, is the offer and CTA immediately clear?>",
    "relevance_to_segment": "<0-10, does this page speak to this audience's specific needs?>",
    "friction_points": "<what on the page creates hesitation or confusion>",
    "drop_off_likelihood": "<0-100, likelihood they leave without converting>",
    "scroll_depth": "<immediate|above_fold|halfway|full_page, how far they'd scroll>"
  }) if has_lp else json.dumps({"skipped": "No landing page provided"})},
  "conversion_stage": {{
    "would_convert": <true|false>,
    "conversion_likelihood": <0-100>,
    "conversion_reasoning": "<specific reason why this segment would or wouldn't complete {conversion_action}>",
    "main_objection": "<the single biggest barrier to conversion for this segment, or null>",
    "trust_score": <0-10>
  }},
  "journey_verdict": {{
    "weakest_stage": "<ad|landing_page|conversion — where the funnel breaks for this segment>",
    "strongest_stage": "<ad|landing_page|conversion — where the journey works best>",
    "funnel_health": "<strong|moderate|weak>",
    "key_insight": "<the single most important finding about this segment's journey — 2-3 sentences>",
    "top_recommendation": "<the one change that would most improve conversion for this segment>"
  }},
  "performance_estimates": {{
    "predicted_ctr": <benchmark_ctr * ctr_multiplier, 2 decimals>,
    "predicted_cvr": <0-20, estimated conversion rate for this segment>,
    "predicted_roas_index": <0.5-3.0, relative ROAS vs industry average>
  }}
}}"""

    if has_lp:
        content = build_vision_content(lp_frames, prompt)
    else:
        content = prompt

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = _default_result()

    result["cluster_id"]    = cluster_id
    result["cluster_label"] = cluster["label"]
    result["cluster_color"] = cluster["color"]
    result["benchmark"]     = benchmark
    return result

def score_journey_for_nemotron(
    segment: dict,
    ad_text: str,
    lp_frames: list,
    conversion_action: str,
    industry: str,
    benchmark: dict
) -> dict:
    name     = segment.get("name", "Segment")
    personas = fetch_nemotron_personas(segment, sample_size=8)
    if not personas:
        personas = fetch_nemotron_personas({"age_min": segment.get("age_min",18), "age_max": segment.get("age_max",99)}, sample_size=8)

    has_lp = len(lp_frames) > 0

    persona_sketches = "\n".join([
        f"- {p.get('age','?')}yo {p.get('sex','')} {(p.get('occupation','') or '').replace('_',' ')} from {p.get('state','')}, interests: {(p.get('hobbies_and_interests') or '')[:80]}"
        for p in personas[:6]
    ])

    lp_instruction = f"\nLANDING PAGE: {len(lp_frames)} screenshot(s) provided above.\nCONVERSION ACTION: {conversion_action}\n" if has_lp else "\nLANDING PAGE: Not provided.\n"

    prompt = f"""You are a search marketing expert evaluating a customer journey on behalf of these specific individuals.

SEGMENT: {name}
INDIVIDUALS:
{persona_sketches}

{ad_text}
{lp_instruction}

Evaluate the complete journey for these specific people — ad → landing page → conversion decision.

Respond ONLY with a JSON object — no preamble, no markdown:
{{
  "ad_stage": {{
    "would_click": <true|false>,
    "click_likelihood": <0-100>,
    "headline_strength": <0-10>,
    "relevance_to_segment": <0-10>,
    "emotional_response": "<positive|neutral|negative|suspicious>",
    "click_reasoning": "<specific to these individuals' backgrounds and interests>",
    "predicted_ctr_multiplier": <0.5-3.0>
  }},
  "landing_page_stage": {json.dumps({"first_impression": "","promise_match": 0,"trust_signals": 0,"clarity": 0,"relevance_to_segment": 0,"friction_points": "","drop_off_likelihood": 0,"scroll_depth": "halfway"}) if has_lp else json.dumps({"skipped": "No landing page provided"})},
  "conversion_stage": {{
    "would_convert": <true|false>,
    "conversion_likelihood": <0-100>,
    "conversion_reasoning": "<specific to these individuals>",
    "main_objection": "<biggest barrier, or null>",
    "trust_score": <0-10>
  }},
  "journey_verdict": {{
    "weakest_stage": "<ad|landing_page|conversion>",
    "strongest_stage": "<ad|landing_page|conversion>",
    "funnel_health": "<strong|moderate|weak>",
    "key_insight": "<most important finding — 2-3 sentences specific to these individuals>",
    "top_recommendation": "<single most impactful change for this segment>"
  }},
  "performance_estimates": {{
    "predicted_ctr": <benchmark_ctr * multiplier, 2 decimals>,
    "predicted_cvr": <0-20>,
    "predicted_roas_index": <0.5-3.0>
  }}
}}"""

    if has_lp:
        content = build_vision_content(lp_frames, prompt)
    else:
        content = prompt

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = _default_result()

    result["cluster_id"]    = f"nemotron_{name.lower().replace(' ','_')}"
    result["cluster_label"] = name
    result["cluster_color"] = "#EE205D"
    result["persona_count"] = len(personas)
    result["benchmark"]     = benchmark
    return result

def _default_result():
    return {
        "ad_stage": {"would_click": False, "click_likelihood": 30, "headline_strength": 5, "relevance_to_segment": 5, "emotional_response": "neutral", "click_reasoning": "N/A", "predicted_ctr_multiplier": 1.0},
        "landing_page_stage": {"first_impression": "N/A", "promise_match": 5, "trust_signals": 5, "clarity": 5, "relevance_to_segment": 5, "friction_points": "N/A", "drop_off_likelihood": 50, "scroll_depth": "halfway"},
        "conversion_stage": {"would_convert": False, "conversion_likelihood": 10, "conversion_reasoning": "N/A", "main_objection": None, "trust_score": 5},
        "journey_verdict": {"weakest_stage": "ad", "strongest_stage": "landing_page", "funnel_health": "weak", "key_insight": "Unable to score.", "top_recommendation": "N/A"},
        "performance_estimates": {"predicted_ctr": 3.17, "predicted_cvr": 3.75, "predicted_roas_index": 1.0}
    }

def aggregate_journey(results: list, benchmark: dict, impressions: int) -> dict:
    if not results: return {}
    avg_ctr     = sum(r["performance_estimates"]["predicted_ctr"] for r in results) / len(results)
    avg_cvr     = sum(r["performance_estimates"]["predicted_cvr"] for r in results) / len(results)
    avg_click   = sum(r["ad_stage"]["click_likelihood"] for r in results) / len(results)
    avg_convert = sum(r["conversion_stage"]["conversion_likelihood"] for r in results) / len(results)
    health_map  = {"strong": 3, "moderate": 2, "weak": 1}
    avg_health  = sum(health_map.get(r["journey_verdict"]["funnel_health"], 1) for r in results) / len(results)
    health_label = "strong" if avg_health >= 2.5 else "moderate" if avg_health >= 1.5 else "weak"
    clicks  = int(impressions * avg_ctr / 100)
    convs   = int(clicks * avg_cvr / 100)
    return {
        "avg_predicted_ctr":         round(avg_ctr, 2),
        "avg_predicted_cvr":         round(avg_cvr, 2),
        "avg_click_likelihood":      round(avg_click, 1),
        "avg_conversion_likelihood": round(avg_convert, 1),
        "estimated_monthly_clicks":  clicks,
        "estimated_monthly_conversions": convs,
        "monthly_impressions":       impressions,
        "benchmark_ctr":             benchmark["avg_ctr"],
        "benchmark_cvr":             benchmark["avg_cvr"],
        "ctr_vs_benchmark":          round(avg_ctr - benchmark["avg_ctr"], 2),
        "cvr_vs_benchmark":          round(avg_cvr - benchmark["avg_cvr"], 2),
        "overall_funnel_health":     health_label,
        "segments_scored":           len(results),
    }

@router.post("/score")
async def score_customer_journey(
    headline_1:          str        = Form(...),
    headline_2:          str        = Form(default=""),
    headline_3:          str        = Form(default=""),
    description_1:       str        = Form(...),
    description_2:       str        = Form(default=""),
    display_url:         str        = Form(default=""),
    target_keyword:      str        = Form(...),
    conversion_action:   str        = Form(default="complete a purchase"),
    industry:            str        = Form(default="default"),
    monthly_impressions: int        = Form(default=10000),
    cluster_ids:         str        = Form(default=""),
    nemotron_segments:   str        = Form(default=""),
    mode:                str        = Form(default="clusters"),
    landing_pages:       list[UploadFile] = File(default=[])
):
    benchmark = INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS["default"])
    ad_text   = build_ad_text(headline_1, headline_2, headline_3, description_1, description_2, display_url, target_keyword)

    # Process landing page files
    lp_frames = []
    lp_meta   = []
    for upload in landing_pages:
        if not upload.filename:
            continue
        ext = os.path.splitext(upload.filename)[1].lower()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            content = await upload.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            lp_data = process_landing_page_file(tmp_path, upload.filename)
            lp_frames.extend(lp_data["frames"])
            lp_meta.append({"filename": upload.filename, "type": lp_data["file_type"], "frames": lp_data["frame_count"]})
        except Exception as e:
            print(f"Landing page processing error {upload.filename}: {e}")
        finally:
            os.unlink(tmp_path)

    # Cap total frames
    lp_frames = lp_frames[:8]
    print(f"Journey scoring: {len(lp_frames)} landing page frames from {len(lp_meta)} files")

    results = []

    if mode == "nemotron" and nemotron_segments:
        segments = json.loads(nemotron_segments)
        for seg in segments:
            try:
                news = get_cluster_news_context(seg.get("name",""), limit=4)
                results.append(score_journey_for_nemotron(seg, ad_text, lp_frames, conversion_action, industry, benchmark))
            except Exception as e:
                print(f"Journey score error for {seg.get('name')}: {e}")
    else:
        ids = json.loads(cluster_ids) if cluster_ids else list(CLUSTERS.keys())
        for cluster_id in ids:
            try:
                news = get_cluster_news_context(cluster_id, limit=4)
                results.append(score_journey_for_cluster(cluster_id, ad_text, lp_frames, conversion_action, industry, benchmark, news))
            except Exception as e:
                print(f"Journey score error for {cluster_id}: {e}")

    return {
        "ad": {
            "headline_1": headline_1, "headline_2": headline_2, "headline_3": headline_3,
            "description_1": description_1, "description_2": description_2,
            "display_url": display_url, "target_keyword": target_keyword,
            "conversion_action": conversion_action, "industry": industry,
        },
        "landing_pages":     lp_meta,
        "has_landing_page":  len(lp_frames) > 0,
        "summary":           aggregate_journey(results, benchmark, monthly_impressions),
        "segment_journeys":  results,
        "benchmark":         benchmark,
    }
