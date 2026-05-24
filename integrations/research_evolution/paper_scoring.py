from __future__ import annotations

import json

from core.llm import ask_json

VALID_ACTIONS = {
    "read_now", "save_for_later", "use_for_grant", "contact_author",
    "use_for_teaching", "use_for_linkedin", "ignore",
}

VALID_USES = {
    "cite_in_grant", "use_for_gap", "support_claim",
    "background_reading", "demonstrate_feasibility", "ignore",
}

# opportunity_type is constrained by the scoring prompt to exactly these
# categorical values (see SCORING_SYSTEM_PROMPT).  Validate it like the
# other categorical fields so an out-of-vocabulary LLM value is coerced.
VALID_OPPORTUNITY_TYPES = {
    "proposal", "paper", "collaboration", "experiment",
    "teaching", "linkedin", "ignore",
}

SCORING_SYSTEM_PROMPT = """\
You are a rigorous scientific evaluator for an OLED/TADF/photophysics/organic-electronics research group
whose strategic focus is red/NIR OLED devices, TADF emitters, lanthanide complexes, and their potential
in biomedical photobiomodulation applications.

Score the paper on the following dimensions (0–10, where 10 is highest):

Core dimensions:
- relevance: Direct relevance to OLED, TADF, organic semiconductor, red-NIR emission, lanthanide complexes, charge transport, device physics.
- novelty: Genuinely new findings, materials, or device strategies — be skeptical of incremental work.
- grant_potential: Fundable novelty, clear societal relevance, alignment with UKRI/ERC/industry call themes.
- collaboration_potential: Authors, institutions, or techniques that offer collaboration value.
- industry_potential: Relevance to OLEDWorks, Universal Display, Samsung Display, LG Display, Merck.
- teaching_public_value: Value for undergraduate teaching, public science communication, LinkedIn posts.
- feasibility: How achievable is replication or extension in a standard organic-electronics academic lab?
- risk: Scientific risk, reliability concern, or reproducibility issue (higher = riskier).

Domain-specific dimensions:
- oled_device_usefulness: Relevance to actual OLED device fabrication, optimisation, or lifetime (0–10).
- tadf_mechanism_relevance: Relevance to TADF photophysics, RISC, ΔEST, singlet/triplet management (0–10).
- red_nir_emission_relevance: Relevance to red/NIR (>600 nm) emission for devices or bio applications (0–10).
- lanthanide_relevance: Relevance to lanthanide sensitisation, f-block photophysics, NIR emitters (0–10).
- experimental_feasibility: Can a well-equipped academic lab replicate or extend this work within 18 months? (0–10).

Also provide:
- agent_commentary: 2–3 sentence expert assessment. Be specific. Do not invent citations.
- evidence_gaps: list of 1–3 specific missing pieces of evidence or unverified claims.
- recommended_action: exactly one of: read_now, save_for_later, use_for_grant, contact_author, use_for_teaching, use_for_linkedin, ignore.
- recommended_use: exactly one of: cite_in_grant, use_for_gap, support_claim, background_reading, demonstrate_feasibility, ignore.
- opportunity_type: the primary opportunity this paper creates — one of: proposal, paper, collaboration, experiment, teaching, linkedin, ignore.

OLED key metrics — extract from the abstract only. Set null if not explicitly stated. Do not infer or estimate.
- key_metrics:
  {
    "emission_wavelength_nm": null,
    "EQE_percent": null,
    "PLQY_percent": null,
    "luminance_cd_m2": null,
    "turn_on_voltage_V": null,
    "DELTA_EST_eV": null,
    "operational_lifetime_hours": null,
    "host_dopant_system": null,
    "device_architecture": null,
    "roll_off": null
  }

Return strict JSON only. No prose outside the JSON."""


def score_paper(profile: dict, paper: dict) -> dict:
    weights = profile.get("scoring_weights", {})
    user_prompt = (
        f"Research profile topics: {', '.join(profile.get('research_topics', [])[:8])}\n\n"
        f"Paper title: {paper.get('title', 'Unknown')}\n"
        f"Source: {paper.get('source', 'unknown')}\n"
        f"Published: {paper.get('published_date', 'unknown')}\n"
        f"Authors: {', '.join((paper.get('authors') or [])[:4])}\n"
        f"Cited by: {paper.get('cited_by_count', 0)}\n\n"
        f"Abstract:\n{paper.get('abstract', 'No abstract available.')[:1500]}\n\n"
        f"Scoring weights: {json.dumps(weights)}\n\n"
        "Score this paper and return strict JSON."
    )
    fallback = {
        "relevance": 5.0, "novelty": 5.0, "grant_potential": 5.0,
        "collaboration_potential": 5.0, "industry_potential": 5.0,
        "teaching_public_value": 5.0, "feasibility": 5.0, "risk": 5.0,
        "oled_device_usefulness": 5.0, "tadf_mechanism_relevance": 5.0,
        "red_nir_emission_relevance": 5.0, "lanthanide_relevance": 5.0,
        "experimental_feasibility": 5.0,
        "agent_commentary": "Score not available.",
        "evidence_gaps": ["LLM scoring failed — manual review needed."],
        "recommended_action": "save_for_later",
        "recommended_use": "background_reading",
        "opportunity_type": "ignore",
        "key_metrics": {},
    }
    try:
        raw = ask_json(SCORING_SYSTEM_PROMPT, user_prompt, temperature=0.1)

        if raw.get("recommended_action") not in VALID_ACTIONS:
            raw["recommended_action"] = "save_for_later"
        if raw.get("recommended_use") not in VALID_USES:
            raw["recommended_use"] = "background_reading"
        # Phase 2 (goal I): validate the prompt-constrained opportunity_type.
        if raw.get("opportunity_type") not in VALID_OPPORTUNITY_TYPES:
            raw["opportunity_type"] = "ignore"

        core_dims = [
            "relevance", "novelty", "grant_potential", "collaboration_potential",
            "industry_potential", "teaching_public_value", "feasibility", "risk",
            "oled_device_usefulness", "tadf_mechanism_relevance",
            "red_nir_emission_relevance", "lanthanide_relevance", "experimental_feasibility",
        ]
        for dim in core_dims:
            # Phase 2 (goal I): clamp every 0–10 dimension to its range.  An
            # LLM returning 15 or -3 previously flowed straight into the
            # weighted total and skewed rankings.
            try:
                raw[dim] = max(0.0, min(10.0, float(raw.get(dim, 5.0))))
            except (TypeError, ValueError):
                raw[dim] = 5.0

        # Ensure key_metrics is a dict
        if not isinstance(raw.get("key_metrics"), dict):
            raw["key_metrics"] = {}

        return raw
    except Exception as exc:
        fallback["evidence_gaps"] = [f"Parse error: {exc}"]
        return fallback


def calculate_total_score(profile: dict, score: dict) -> float:
    """
    Weighted score using profile weights for core dimensions.
    Domain-specific dimensions (oled_device_usefulness etc.) contribute a small bonus
    when they are above 5, so high domain relevance slightly lifts the total.
    """
    weights = profile.get("scoring_weights", {
        "relevance": 0.30, "novelty": 0.22, "grant_potential": 0.18,
        "collaboration_potential": 0.12, "industry_potential": 0.08,
        "teaching_public_value": 0.10,
    })
    total = sum(score.get(dim, 5.0) * w for dim, w in weights.items())

    feasibility_bonus = (score.get("feasibility", 5.0) - 5.0) * 0.05
    risk_penalty = (score.get("risk", 5.0) - 5.0) * 0.05

    # Domain bonus: average of oled/tadf/red-nir/lanthanide above 5 → small lift
    domain_dims = [
        "oled_device_usefulness", "tadf_mechanism_relevance",
        "red_nir_emission_relevance", "lanthanide_relevance",
    ]
    domain_above_mid = sum(
        max(0.0, score.get(d, 5.0) - 5.0) for d in domain_dims
    ) / len(domain_dims)
    domain_bonus = domain_above_mid * 0.04

    total = total + feasibility_bonus - risk_penalty + domain_bonus
    return round(max(0.0, min(10.0, total)), 3)


def score_papers(profile: dict, papers: list[dict]) -> list[dict]:
    scored: list[dict] = []
    for paper in papers:
        if "source_error" in paper or "source_errors" in paper:
            continue
        s = score_paper(profile, paper)
        total = calculate_total_score(profile, s)
        merged = {**paper, **s, "total_score": total}
        scored.append(merged)
    scored.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return scored
