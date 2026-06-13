from __future__ import annotations

from rentivo.communications.moderation import ModerationResult, scan


def test_clean_text_is_not_flagged():
    r = scan("Prezado João, segue a cobrança do mês. Atenciosamente.")
    assert r.severe == ()
    assert r.mild == ()
    assert not r.blocked
    assert not r.flagged


def test_mild_profanity_is_flagged_not_blocked():
    r = scan("Que merda de situação, paga logo.")
    assert "merda" in r.mild
    assert r.severe == ()
    assert r.flagged
    assert not r.blocked


def test_severe_threat_phrase_blocks():
    r = scan("Se não pagar vou te matar.")
    assert "vou te matar" in r.severe
    assert r.blocked
    assert r.flagged


def test_subject_and_body_scanned_together():
    r = scan("Aviso\nseu merda")
    assert "merda" in r.mild


def test_normalization_handles_accents_leetspeak_and_repeats():
    for variant in ("mérda", "m3rda", "merdaaaa", "MERDA"):
        assert "merda" in scan(variant).mild, variant


def test_word_boundary_avoids_false_positives():
    r = scan("Analista de cuca fresca classe A")
    assert r.mild == ()
    assert r.severe == ()


def test_empty_text_is_safe():
    r = scan("")
    assert r == ModerationResult(severe=(), mild=())


def test_matches_are_sorted_and_deduped():
    r = scan("merda merda porra")
    assert r.mild == ("merda", "porra")


def test_whitespace_does_not_evade_severe_phrase():
    assert scan("vou  te  matar").blocked  # double spaces
    assert scan("vou\nte matar").blocked  # newline (subject + body join)


def test_leetspeak_severe_phrase_blocks():
    assert "vou te matar" in scan("v0u te m4tar").severe
