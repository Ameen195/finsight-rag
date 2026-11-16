import logging

import pytest

from finsight.ingest.cli import apply_glyph_map

RUPEE = {"`": "₹"}


def test_glyph_map_replaces_text_and_caption_without_mutating_input() -> None:
    els = [{"type": "table", "text": "| (In `) | `1,022 crore |", "page": 1, "caption": "` crore"}]
    out = apply_glyph_map(els, RUPEE)
    assert out[0]["text"] == "| (In ₹) | ₹1,022 crore |" and out[0]["caption"] == "₹ crore"
    assert els[0]["text"].count("`") == 2  # cache data untouched
    assert apply_glyph_map(els, {}) is els


@pytest.mark.parametrize(
    ("raw", "expected"),
    [  # unit labels from the Infosys report that are not followed by a digit or "crore"
        ("(In `)", "(In ₹)"),
        ("Equity shares of par value ` 5/- each", "Equity shares of par value ₹ 5/- each"),
        ("Dividend per share (`) (1)", "Dividend per share (₹) (1)"),
        ("(in ` - crore)", "(in ₹ - crore)"),
        ("net book value: ` Nil", "net book value: ₹ Nil"),
    ],
)
def test_glyph_map_handles_unit_labels(raw: str, expected: str) -> None:
    assert apply_glyph_map([{"type": "text", "text": raw, "page": 1}], RUPEE)[0]["text"] == expected


def test_glyph_map_logs_replacement_count(caplog: pytest.LogCaptureFixture) -> None:
    els = [{"type": "text", "text": "` 5 and `6", "page": 1, "caption": "(`)"}]
    with caplog.at_level(logging.INFO):
        apply_glyph_map(els, RUPEE)
    assert "3 replacements" in caplog.text
