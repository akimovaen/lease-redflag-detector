from lease_redflag_detector.extraction.quotes import quote_in_text

TEXT = "The Tenant may terminate this Lease\nby giving  three months' notice."


def test_exact_quote_is_found():
    assert quote_in_text("The Tenant may terminate this Lease", TEXT)


def test_quote_across_line_break_is_found():
    assert quote_in_text("this Lease by giving three months' notice.", TEXT)


def test_changed_wording_is_not_found():
    assert not quote_in_text("The Tenant may end this Lease", TEXT)


def test_empty_quote_is_not_found():
    assert not quote_in_text("  ", TEXT)
