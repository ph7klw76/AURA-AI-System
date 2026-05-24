"""
ToolUniverse curated category whitelist.

Only the explicitly listed categories are enabled in the ToolUniverse MCP server.
All other categories (including all biomedical-research tools) are disabled.
"""

ENABLED_CATEGORIES: list[str] = [
    "python_executor",
    "software_scientific_computing",
    "software_machine_learning",
    "rdkit_cheminfo",
    "software_cheminformatics",
    "embedding",
    "semantic_scholar",
    "OpenAlex",
    "crossref",
    "arxiv",
    "github",
    "huggingface",
    "tool_composition",
    "agents",
    "tool_discovery_agents",
    "output_summarization",
    "data_quality",
    "uspto",
    "mcp_auto_loader_uspto_downloader",
    "chem_compute",
    "crystal_structure",
    "cod_crystal",
    "smiles_verify",
    "visualization_molecule_2d",
    "visualization_molecule_3d",
    "software_visualization",
    "scite",
    "unpaywall",
    "datacite",
    "zenodo",
]


def run():
    """Entry point: launch ToolUniverse stdio server with curated categories only."""
    import sys

    categories = sorted(ENABLED_CATEGORIES)
    print(f"ToolUniverse categories enabled: {len(categories)}", file=sys.stderr)
    for c in categories:
        print(f"  - {c}", file=sys.stderr)

    from tooluniverse.smcp_server import run_stdio_server
    sys.argv = [
        "tooluniverse-smcp-stdio",
        "--categories", *categories,
    ]
    run_stdio_server()


if __name__ == "__main__":
    run()
