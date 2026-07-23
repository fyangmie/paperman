from paperman.downloaders.publisher import PUBLISHER_PATTERNS


def test_common_prefixes():
    """Verify all common DOI prefixes have patterns."""
    prefixes = [
        "10.1016",   # Elsevier
        "10.1038",   # Nature
        "10.1126",   # Science
        "10.1161",   # AHA Journals
        "10.1186",   # Springer/BioMed Central
        "10.1007",   # Springer
        "10.1093",   # Oxford
        "10.3390",   # MDPI
        "10.1111",   # Wiley
        "10.1021",   # ACS
        "10.1172",   # JCI
        "10.1073",   # PNAS
        "10.1371",   # PLOS
    ]
    for p in prefixes:
        assert p in PUBLISHER_PATTERNS, f"Missing pattern for {p}"


def test_pattern_format():
    """URL patterns contain template placeholders."""
    for doi_prefix, pattern in PUBLISHER_PATTERNS.items():
        assert "{doi}" in pattern or "{suffix}" in pattern, \
            f"Pattern for {doi_prefix} has no template vars: {pattern}"
