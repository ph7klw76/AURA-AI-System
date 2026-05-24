"""Quick demo of the three Wave 1 routing pipelines."""
from agents.strategic_governor import _derive_backward_compat
from core.schemas import GovernorDecision, MemoryPolicy, SelfEvolutionPolicy


def base():
    return GovernorDecision(
        task_type="research_scan", priority="medium",
        selected_agents=[], research_scout_mode="none",
        memory_policy=MemoryPolicy(),
        self_evolution_policy=SelfEvolutionPolicy(run=True, reason="."),
    )


cases = [
    ("GRANT",          "Turn this OLED idea into a grant proposal structure."),
    ("TEACHING",       "Explain TADF OLEDs to undergraduate students."),
    ("RESEARCH+TEACH", "Find recent papers on TADF and explain them to undergraduate students."),
    ("IDEATE+TEACH",   "Explore my OLED research idea and turn it into a lecture for graduate students."),
]
arrow = " -> "
for label, prompt in cases:
    d = _derive_backward_compat(base(), prompt)
    pipeline = arrow.join(d.selected_agents)
    print(f"{label:18s}  pipeline: {pipeline}")
    print(f"{'':18s}  scout_mode: {d.research_scout_mode}")
    print()
