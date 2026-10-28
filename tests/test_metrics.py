from lease_redflag_detector.extraction.metrics import (
    field_correct,
    percentile,
    strings_match,
)

GOLDEN = {
    "lessor": "Shanghai New Cogi Cosmetic Co., Ltd.",
    "area": {"value": 967.38, "unit": "sqm"},
    "rent": {"amount": 85330.0, "currency": "CNY", "period": "month"},
    "end_date": None,
}


def test_strings_ignore_case_and_punctuation():
    assert strings_match(
        "Shanghai New Cogi Cosmetic Co., Ltd.", "SHANGHAI NEW COGI COSMETIC CO LTD"
    )


def test_different_names_do_not_match():
    assert not strings_match(
        "Shanghai New Cogi Cosmetic Co., Ltd.", "Shanghai Mecox Lane Co., Ltd."
    )


def test_null_matches_only_null():
    assert field_correct("end_date", GOLDEN, {"end_date": None})
    assert not field_correct("end_date", GOLDEN, {"end_date": "2012-08-19"})
    assert not field_correct("lessor", GOLDEN, {"lessor": None})


def test_numbers_within_tolerance():
    assert field_correct("area", GOLDEN, {"area": {"value": 967.0, "unit": "sqm"}})
    assert not field_correct(
        "area", GOLDEN, {"area": {"value": 967.38, "unit": "sqft"}}
    )


def test_rent_needs_period_and_currency():
    assert field_correct(
        "rent",
        GOLDEN,
        {"rent": {"amount": 85330, "currency": "cny", "period": "month"}},
    )
    assert not field_correct(
        "rent", GOLDEN, {"rent": {"amount": 85330, "currency": "CNY", "period": "year"}}
    )


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([5], 0.95) == 5
