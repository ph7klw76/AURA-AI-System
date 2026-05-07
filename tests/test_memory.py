import json
import tempfile
from pathlib import Path

import pytest

import config


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
    monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")


def test_save_and_read_memory(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    from core.memory import save_memory, read_jsonl
    save_memory("lesson", "TADF emitters show high EQE", {"topic": "OLED"})
    records = read_jsonl(config.MEMORY_PATH)
    assert len(records) == 1
    assert records[0]["content"] == "TADF emitters show high EQE"
    assert records[0]["kind"] == "lesson"


def test_read_jsonl_empty(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    from core.memory import read_jsonl
    records = read_jsonl(config.MEMORY_PATH)
    assert records == []


def test_retrieve_relevant_memory(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    from core.memory import save_memory, retrieve_relevant_memory
    save_memory("lesson", "OLED device efficiency depends on charge balance")
    save_memory("lesson", "Python testing with pytest is reliable")
    results = retrieve_relevant_memory("OLED efficiency")
    assert len(results) >= 1
    assert any("OLED" in r["content"] for r in results)


def test_save_reflection(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    from core.memory import save_reflection, read_jsonl
    save_reflection({"what_worked": ["paper scoring"], "reusable_lessons": []})
    records = read_jsonl(config.REFLECTION_PATH)
    assert len(records) == 1
    assert "what_worked" in records[0]
