import json
from pathlib import Path

import pytest

from app.additions import chatgpt_content_response_runtime as reader
from app.additions import chatgpt_json_recovery_runtime as parser


AGRICOLA = "Agricola - Agriculture and Organic Farm WordPress Theme"
RAW = (Path(__file__).parent / "fixtures/agricola_dom_response.txt").read_text(encoding="utf-8")
PAYLOAD = parser.extract_json(RAW)


@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "```\n{}\n```",
                                     'Texto "antes\n```json\n{}\n```\nTexto depois'])
def test_exact_agricola_dom_response(wrapper):
    result = reader.parse_content_response(wrapper.format(RAW), {
        "product_name": AGRICOLA, "developer": "Ultrapack",
        "official_url": PAYLOAD["official_url"].strip(),
    })
    assert result["product_name"] == AGRICOLA
    assert result["official_url"].endswith("39853177")
    assert result["developer"] == "Ultrapack"
    assert parser.response_kind(RAW, AGRICOLA) == "content_json_dom_repaired"


def test_pure_json_nested_arrays_braces_escaped_quotes_and_trailing_commas():
    payload = {**PAYLOAD, "nested": {"array": [{"text": 'Brace } and { and quote " and slash \\'}, [1, 2]]}}
    pure = json.dumps(payload)
    assert parser.extract_json(pure, AGRICOLA) == payload
    trailing = pure[:-1] + ', "extra": [1, {"x": 2,},],}'
    assert parser.extract_json(trailing, AGRICOLA)["nested"] == payload["nested"]


def test_selects_matching_content_not_last_incidental_or_other_product_object():
    wrong = json.dumps({**PAYLOAD, "product_name": "Other Product"})
    text = wrong + "\n" + RAW + '\n{"debug":true}\n' + wrong
    assert parser.extract_json(text, AGRICOLA)["product_name"] == AGRICOLA


@pytest.mark.parametrize("value", ['literal \\_name', 'literal \\<tag\\>', 'a \\\\_ b',
                                   'quote " brace } tab\t line\n slash\\'])
def test_valid_json_escapes_survive_repeated_dom_normalization(value):
    payload = {**PAYLOAD, "extra": value}
    text = json.dumps(payload)
    assert parser.extract_json(reader._rendered_text(text), AGRICOLA) == payload


@pytest.mark.parametrize("control", [chr(i) for i in range(32)])
def test_dom_controls_inside_string_preserve_complete_structure(control):
    text = json.dumps(PAYLOAD).replace('"official_url": "', '"official_url": "' + control)
    assert parser.extract_json(text, AGRICOLA)["official_url"].strip() == PAYLOAD["official_url"].strip()


@pytest.mark.parametrize("text", [RAW[:-2], RAW[:-10], '{"outer":' + RAW,
                                 json.dumps({**PAYLOAD, "product_name": "Other Product"}),
                                 json.dumps({k: v for k, v in PAYLOAD.items() if k != "product_name"})])
def test_incomplete_or_wrong_identity_never_persists(text):
    assert parser.extract_json(text, AGRICOLA) is None
    with pytest.raises(RuntimeError):
        reader.parse_content_response(text, {"product_name": AGRICOLA})


@pytest.mark.parametrize(("text", "kind"), [
    ("", "content_no_response"),
    (RAW[:-2], "content_response_partial"),
    ('{"product_name": broken}', "content_json_invalid"),
    (json.dumps({**PAYLOAD, "product_name": "Wrong"}), "content_product_mismatch"),
])
def test_diagnostic_distinguishes_failure_modes(text, kind):
    assert parser.response_kind(text, AGRICOLA) == kind


def test_completed_stable_response_wins_over_stale_stop(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(reader.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(reader.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(reader, "_body_text", lambda page: "")
    monkeypatch.setattr(reader, "_submit", lambda page, prompt: None)
    monkeypatch.setattr(reader, "_conversation_candidates", lambda page, marker: [RAW])
    monkeypatch.setattr(reader, "_assistant_busy", lambda page: True)
    monkeypatch.setattr(reader.legacy, "_looks_like_auth_wall", lambda page: False)
    monkeypatch.setattr(reader.legacy, "_update_job_state", lambda *a, **kw: None)
    result = reader._wait_content_response(object(), "prompt", 20, {"job_id": "a", "product_name": AGRICOLA})
    assert result == RAW
    assert 8 <= clock[0] < 10


def test_once_complete_but_now_truncated_is_not_accepted_at_timeout(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(reader.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(reader.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(reader, "_body_text", lambda page: "")
    monkeypatch.setattr(reader, "_submit", lambda page, prompt: None)
    monkeypatch.setattr(reader, "_conversation_candidates", lambda page, marker: [RAW if clock[0] == 0 else RAW[:-2]])
    monkeypatch.setattr(reader, "_assistant_busy", lambda page: True)
    monkeypatch.setattr(reader.legacy, "_looks_like_auth_wall", lambda page: False)
    from app.additions import chatgpt_playwright_compat as compat
    monkeypatch.setattr(compat, "_diagnostic", lambda page, reason: "test.json")
    with pytest.raises(RuntimeError, match="parcialmente"):
        reader._wait_content_response(object(), "prompt", 2, {"job_id": "a", "product_name": AGRICOLA})
