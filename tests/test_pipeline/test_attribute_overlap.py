from matcher.pipeline.scoring import compute_attribute_overlap


def test_attribute_overlap_identical():
    q = {"brand": "bosch", "unit": "шт", "numbers": [25, 40]}
    c = {"brand": "bosch", "unit": "шт", "numbers": [25, 40]}
    assert compute_attribute_overlap(q, c) == 1.0


def test_attribute_overlap_partial():
    q = {"brand": "bosch", "unit": "шт", "numbers": [25]}
    c = {"brand": "bosch", "unit": "м", "numbers": [25]}
    score = compute_attribute_overlap(q, c)
    assert 0.3 < score < 0.9


def test_attribute_overlap_no_attributes():
    assert compute_attribute_overlap({}, {}) == 0.0


def test_attribute_overlap_none_values_ignored():
    q = {"brand": "bosch", "model": None}
    c = {"brand": "bosch", "model": None}
    assert compute_attribute_overlap(q, c) == 1.0
