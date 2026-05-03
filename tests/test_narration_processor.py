"""Tests for narration_processor.validate_narration_density."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from narration_processor import (
    TARGET_WPM_MAX,
    TARGET_WPM_MIN,
    _word_count,
    scrub_closing_ctas,
    strip_outro_ctas,
    validate_narration_density,
)


@dataclass
class FakeScene:
    """Minimal stand-in matching the attributes the validator reads."""

    scene_id: str
    narration: str
    audio_duration: float | None = None
    estimated_duration: float | None = None


class TestWordCount:
    def test_basic(self):
        assert _word_count("hello world") == 2

    def test_empty(self):
        assert _word_count("") == 0

    def test_punctuation_stripped(self):
        # "It's" splits into ("It", "s") on the apostrophe — bare words count cleanly
        assert _word_count("Hello, world! It is fine.") == 5

    def test_contractions_count_as_two_words(self):
        # \w+ splits on the apostrophe
        assert _word_count("you'll") == 2

    def test_multiline(self):
        assert _word_count("one two\nthree four\tfive") == 5


class TestDensityWarnings:
    def test_warns_above_max_wpm(self, caplog):
        # 50 words in 10s -> 300 WPM, well above 145
        scene = FakeScene("dense", "word " * 50, audio_duration=10.0)
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density([scene])
        assert any("dense" in r.message and "300 WPM" in r.message for r in caplog.records)

    def test_silent_when_in_range(self, caplog):
        # 24 words in 10s -> 144 WPM, just under cap
        scene = FakeScene("ok", "word " * 24, audio_duration=10.0)
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density([scene])
        assert not caplog.records

    def test_silent_at_exact_max(self, caplog):
        # 145 WPM exactly should NOT warn (warning is strict >)
        scene = FakeScene("edge", "word " * 145, audio_duration=60.0)
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density([scene])
        assert not caplog.records

    def test_falls_back_to_estimated_duration(self, caplog):
        scene = FakeScene("est", "word " * 50, audio_duration=None, estimated_duration=10.0)
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density([scene])
        assert any("est" in r.message for r in caplog.records)

    def test_falls_back_to_default_15s(self, caplog):
        # Both durations missing -> default 15s. 100 words / 15s = 400 WPM
        scene = FakeScene("nodur", "word " * 100, audio_duration=None, estimated_duration=None)
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density([scene])
        assert any("nodur" in r.message for r in caplog.records)

    def test_empty_narration_does_not_warn(self, caplog):
        scene = FakeScene("blank", "", audio_duration=10.0)
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density([scene])
        assert not caplog.records

    def test_multiple_scenes_independent(self, caplog):
        scenes = [
            FakeScene("ok", "word " * 20, audio_duration=10.0),       # 120 WPM
            FakeScene("hot", "word " * 80, audio_duration=10.0),      # 480 WPM
            FakeScene("ok2", "word " * 10, audio_duration=10.0),      # 60 WPM
        ]
        with caplog.at_level(logging.WARNING, logger="narration_processor"):
            validate_narration_density(scenes)
        warned_ids = [r.message for r in caplog.records]
        assert any("hot" in m for m in warned_ids)
        assert not any("'ok'" in m or "'ok2'" in m for m in warned_ids)


class TestThresholdConstants:
    def test_target_range_is_sane(self):
        assert 100 <= TARGET_WPM_MIN < TARGET_WPM_MAX <= 180


class TestStripOutroCTAs:
    def test_removes_thanks_for_watching(self):
        text = "PKCE binds the auth code to the verifier. Thanks for watching!"
        out = strip_outro_ctas(text)
        assert "thanks for watching" not in out.lower()
        assert "PKCE binds the auth code to the verifier" in out

    def test_removes_subscribe_variants(self):
        for tail in (
            "Like and subscribe!",
            "Don't forget to subscribe.",
            "Hit the bell.",
            "Please subscribe.",
            "See you next time.",
        ):
            text = f"And that's the trick. {tail}"
            out = strip_outro_ctas(text)
            assert tail.lower().split()[0] not in out.lower(), f"failed on: {tail}"

    def test_preserves_unrelated_content(self):
        text = "The handshake takes three round trips."
        assert strip_outro_ctas(text) == text

    def test_handles_empty(self):
        assert strip_outro_ctas("") == ""
        assert strip_outro_ctas(None) is None

    def test_collapses_whitespace(self):
        text = "Final point.   Thanks for watching!   "
        out = strip_outro_ctas(text)
        assert "  " not in out
        assert out.endswith(".")


class TestScrubClosingCTAs:
    def test_only_last_scene_modified(self):
        scenes = [
            FakeScene("intro", "Welcome. Let's go."),
            FakeScene("middle", "Here is step two. Thanks for watching."),  # not last
            FakeScene("outro", "And that's it. Thanks for watching!"),
        ]
        scrub_closing_ctas(scenes)
        assert "Thanks for watching" in scenes[1].narration  # untouched
        assert "thanks for watching" not in scenes[2].narration.lower()

    def test_empty_scenes_no_crash(self):
        scrub_closing_ctas([])  # should not raise

    def test_never_empties_narration(self):
        # If the entire narration is a CTA, keep the original (don't blank it)
        scenes = [FakeScene("only", "Thanks for watching!")]
        scrub_closing_ctas(scenes)
        assert scenes[0].narration  # not empty
