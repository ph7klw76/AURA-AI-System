import pytest
from unittest.mock import patch, MagicMock


MOCK_OPENALEX_RESPONSE = {
    "results": [
        {
            "title": "TADF emitters for red OLED devices",
            "primary_location": {"landing_page_url": "https://example.com/paper1"},
            "abstract_inverted_index": {"TADF": [0], "emitters": [1], "red": [2]},
            "authorships": [{"author": {"display_name": "Dr. Smith"}}],
            "publication_date": "2024-03-15",
            "cited_by_count": 12,
        }
    ]
}

MOCK_ARXIV_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Lanthanide near-infrared OLED emitters</title>
    <summary>We report efficient NIR OLED devices based on lanthanide complexes.</summary>
    <id>https://arxiv.org/abs/2401.00001</id>
    <published>2024-01-10T00:00:00Z</published>
    <author><name>Dr. Chen</name></author>
  </entry>
</feed>"""


def test_search_openalex_returns_normalized_paper():
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_OPENALEX_RESPONSE
    mock_resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_resp):
        from integrations.research_evolution.paper_sources import search_openalex
        papers = search_openalex("TADF OLED", max_results=1)
    assert len(papers) == 1
    assert papers[0]["source"] == "openalex"
    assert "TADF" in papers[0]["title"]
    assert "unique_key" in papers[0]


def test_search_arxiv_returns_normalized_paper():
    mock_resp = MagicMock()
    mock_resp.content = MOCK_ARXIV_XML
    mock_resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_resp):
        from integrations.research_evolution.paper_sources import search_arxiv
        papers = search_arxiv("lanthanide OLED", max_results=1)
    assert len(papers) == 1
    assert papers[0]["source"] == "arxiv"
    assert "Lanthanide" in papers[0]["title"]


def test_api_failure_does_not_crash():
    with patch("requests.get", side_effect=ConnectionError("Network down")):
        from integrations.research_evolution.paper_sources import search_openalex
        result = search_openalex("OLED", max_results=3)
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "source_error" in result[0]


def test_deduplicate_removes_duplicates():
    from integrations.research_evolution.paper_sources import deduplicate_papers
    papers = [
        {"title": "Paper A", "url": "https://x.com/a", "unique_key": "key1", "source": "openalex"},
        {"title": "Paper A", "url": "https://x.com/a", "unique_key": "key1", "source": "arxiv"},
        {"title": "Paper B", "url": "https://x.com/b", "unique_key": "key2", "source": "arxiv"},
    ]
    deduped = deduplicate_papers(papers)
    assert len(deduped) == 2
