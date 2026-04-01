"""Tests for golden set structure validation."""

import json
from pathlib import Path

GOLDEN_SET_PATH = Path(__file__).parent.parent / "golden_set" / "test_queries.json"


class TestGoldenSetStructure:
    def test_golden_set_loads(self):
        with open(GOLDEN_SET_PATH) as f:
            data = json.load(f)
        assert data["total_queries"] == 302
        assert len(data["queries"]) == 302

    def test_queries_have_required_fields(self):
        with open(GOLDEN_SET_PATH) as f:
            data = json.load(f)
        required = {"query_id", "raw_query", "expected_product_hint", "category", "difficulty"}
        for q in data["queries"]:
            assert required.issubset(q.keys()), f"Missing fields in {q.get('query_id')}"

    def test_difficulty_distribution(self):
        with open(GOLDEN_SET_PATH) as f:
            data = json.load(f)
        difficulties = [q["difficulty"] for q in data["queries"]]
        assert set(difficulties) == {"easy", "medium", "hard"}
        assert difficulties.count("easy") == 111
        assert difficulties.count("medium") == 137
        assert difficulties.count("hard") == 54
