from pebench.literature.harvest import _base_quality_features, _is_strict_flyback_seed, normalize_doi


def test_normalize_doi_strips_url_prefix() -> None:
    assert normalize_doi("https://doi.org/10.1109/TPEL.2024.1234567") == "10.1109/tpel.2024.1234567"


def test_quality_features_reward_design_relevant_flyback_records() -> None:
    record = {
        "title": "High-efficiency isolated flyback converter design",
        "abstract": "This paper presents a 65 W flyback converter with 24 V output, 2.7 A load, 91% efficiency and 40 mV ripple.",
        "citation_count": 18,
        "is_open_access": True,
        "pdf_url": "https://example.org/paper.pdf",
        "doi": "10.1000/example",
        "year": 2024,
        "venue": "IEEE Transactions on Power Electronics",
    }
    features = _base_quality_features(record)
    assert features["design_relevant"] is True
    assert features["quality_bucket"] == "high"
    assert features["task_readiness"] in {"high", "medium"}


def test_quality_features_penalize_irrelevant_flyback_usage() -> None:
    record = {
        "title": "Television flyback deflection control",
        "abstract": "A cathode ray display deflection circuit using a flyback transformer.",
        "citation_count": 5,
        "is_open_access": False,
        "pdf_url": None,
        "doi": None,
        "year": 1998,
        "venue": "Display Systems Journal",
    }
    features = _base_quality_features(record)
    assert features["design_relevant"] is False
    assert features["quality_bucket"] != "high"


def test_strict_seed_requires_flyback_in_title() -> None:
    assert _is_strict_flyback_seed({"title": "Active Clamp Flyback Converter for USB PD"}) is True
    assert _is_strict_flyback_seed({"title": "Isolated Flying Capacitor Multilevel Converters"}) is False
