"""Schema faithfulness: exact decimals, stable JSON shape, no float drift."""

import json
from decimal import Decimal

from wd_reader import read_document
from wd_reader.schema import (
    Citation,
    Classification,
    HealthAndWelfare,
    WageDetermination,
)
from wd_reader.sources import TextLayerExtractor

from wd_reader_fixtures import WD_TEXTLAYER_CLEAN


def test_rates_are_exact_decimals_not_floats():
    wd = WageDetermination(
        classifications=[
            Classification(code="11150", title="Janitor",
                           base_rate_per_hour=Decimal("17.56"))
        ]
    )
    d = wd.to_dict()
    rate = d["classifications"][0]["base_rate_per_hour"]
    assert isinstance(rate, Decimal)
    assert rate == Decimal("17.56")


def test_json_renders_rates_faithfully():
    hw = HealthAndWelfare(rate_per_hour=Decimal("5.55"), weekly=Decimal("222.08"),
                          monthly=Decimal("962.08"))
    hw._meta.citation = Citation(page=8, span="line 120")
    wd = WageDetermination(wd_number="2015-5657", health_and_welfare=hw)
    text = wd.to_json()
    parsed = json.loads(text)
    assert parsed["health_and_welfare"]["rate_per_hour"] == 5.55
    assert parsed["health_and_welfare"]["weekly"] == 222.08
    assert parsed["health_and_welfare"]["_meta"]["citation"]["page"] == 8


def test_output_has_all_required_top_level_keys():
    res = read_document(TextLayerExtractor.from_text(WD_TEXTLAYER_CLEAN))
    d = res.wage_determination.to_dict()
    for key in (
        "wd_number", "revision", "revision_date", "wd_type", "locality",
        "health_and_welfare", "vacation", "holidays", "classifications",
        "extraction_meta",
    ):
        assert key in d, f"missing top-level key {key}"


def test_every_classification_has_meta_confidence_and_citation():
    res = read_document(TextLayerExtractor.from_text(WD_TEXTLAYER_CLEAN))
    for c in res.wage_determination.classifications:
        assert 0.0 <= c._meta.confidence <= 1.0
        assert c._meta.citation is not None


def test_extraction_meta_is_populated():
    res = read_document(TextLayerExtractor.from_text(WD_TEXTLAYER_CLEAN))
    em = res.wage_determination.extraction_meta
    assert em.source_type.value in ("text_layer", "ocr")
    assert isinstance(em.overall_confidence, float)
    assert isinstance(em.fields_requiring_confirmation, list)
