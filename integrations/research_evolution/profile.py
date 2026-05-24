from __future__ import annotations

from pathlib import Path

import yaml

import config

PROTECTED_TOPICS = [
    "OLED",
    "TADF",
    "organic semiconductor",
    "quantum chemistry",
    "red-NIR emission",
    "lanthanide complex",
    "charge transport",
    "device degradation",
]

DEFAULT_PROFILE = {
    "research_topics": [
        "OLED",
        "TADF",
        "organic semiconductor",
        "red-NIR emission",
        "lanthanide complex",
        "exciplex system",
        "charge transport",
        "molecular vibration",
        "device degradation",
        "machine learning materials discovery",
        "quantum chemistry",
    ],
    "scoring_weights": {
        "relevance": 0.30,
        "novelty": 0.22,
        "grant_potential": 0.18,
        "collaboration_potential": 0.12,
        "industry_potential": 0.08,
        "teaching_public_value": 0.10,
    },
    "watchlist": {
        "researchers": [],
        "institutions": [],
        "companies": [
            "OLEDWorks",
            "Universal Display Corporation",
            "Samsung Display",
            "LG Display",
            "Merck",
        ],
    },
    "negative_filters": [
        "inorganic LED",
        "perovskite solar cell",
        "silicon photovoltaic",
    ],
    "protected_topics": PROTECTED_TOPICS,
}


def create_default_profile_if_missing() -> None:
    path: Path = config.RESEARCH_PROFILE_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULT_PROFILE, f, default_flow_style=False, allow_unicode=True)


def load_research_profile() -> dict:
    create_default_profile_if_missing()
    with open(config.RESEARCH_PROFILE_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or DEFAULT_PROFILE.copy()


def save_research_profile(profile: dict) -> None:
    with open(config.RESEARCH_PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return weights
    return {k: round(v / total, 4) for k, v in weights.items()}


def sanitize_profile_update(proposed: dict, current: dict) -> dict:
    sanitized = proposed.copy()

    # Preserve protected topics
    current_topics = set(current.get("research_topics", []))
    proposed_topics = set(proposed.get("research_topics", []))
    protected = set(PROTECTED_TOPICS)
    sanitized["research_topics"] = list(dict.fromkeys(
        list(protected & (current_topics | proposed_topics)) +
        [t for t in proposed_topics if t not in protected]
    ))

    # Normalize weights
    weights = proposed.get("scoring_weights", current.get("scoring_weights", {}))
    sanitized["scoring_weights"] = normalize_weights(weights)

    # Remove negative filters that conflict with protected topics
    neg_filters = [
        f for f in proposed.get("negative_filters", [])
        if not any(pt.lower() in f.lower() for pt in PROTECTED_TOPICS)
    ]
    sanitized["negative_filters"] = list(dict.fromkeys(neg_filters))

    # Ensure protected_topics section
    sanitized["protected_topics"] = PROTECTED_TOPICS

    return sanitized
