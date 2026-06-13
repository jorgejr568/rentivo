from __future__ import annotations

from rentivo.communications.defaults import (
    DEFAULT_BILL_READY_BODY,
    DEFAULT_BILL_READY_SUBJECT,
    system_default_template,
)


def test_default_body_contains_expected_placeholders():
    for token in ("{{nome_inquilino}}", "{{unidade}}", "{{mes}}"):
        assert token in DEFAULT_BILL_READY_BODY


def test_default_subject_is_non_empty():
    assert DEFAULT_BILL_READY_SUBJECT.strip()


def test_system_default_template_shape():
    tmpl = system_default_template("bill_ready")
    assert tmpl.id is None
    assert tmpl.owner_type == "system"
    assert tmpl.owner_id == 0
    assert tmpl.comm_type == "bill_ready"
    assert tmpl.subject == DEFAULT_BILL_READY_SUBJECT
    assert tmpl.body_markdown == DEFAULT_BILL_READY_BODY
