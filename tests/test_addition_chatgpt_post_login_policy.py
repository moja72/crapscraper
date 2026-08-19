from __future__ import annotations

import app.addition_chatgpt_post_login_policy as policy


def test_project_target_wins_over_stale_login_target(monkeypatch) -> None:
    events: list[tuple[str, str, int]] = []

    monkeypatch.setattr(policy.cdp, "_browser_ready", lambda _endpoint: True)
    monkeypatch.setattr(
        policy.coproducao,
        "_target_urls",
        lambda _endpoint: [
            "https://auth.openai.com/log-in",
            policy.coproducao._PROJECT_URL,
        ],
    )
    monkeypatch.setattr(
        policy.one_click,
        "_emit",
        lambda _job_id, message, *, step="", progress=None: events.append(
            (message, step, int(progress or 0))
        ),
    )

    policy._wait_login_then_project_fixed(
        "job-1",
        "http://127.0.0.1:9444",
        policy.coproducao._PROJECT_URL,
        timeout_seconds=1,
    )

    assert events
    assert events[-1][1] == "chatgpt_project"
    assert events[-1][2] == 14
    assert "Sessão autenticada" in events[-1][0]


def test_home_after_login_reopens_project(monkeypatch) -> None:
    opened: list[str] = []
    sequences = iter(
        [
            ["https://chatgpt.com/"],
            [policy.coproducao._PROJECT_URL],
        ]
    )

    monkeypatch.setattr(policy.cdp, "_browser_ready", lambda _endpoint: True)
    monkeypatch.setattr(policy.coproducao, "_target_urls", lambda _endpoint: next(sequences))
    monkeypatch.setattr(policy.cdp, "_open_project_tab", lambda _endpoint, url: opened.append(url))
    monkeypatch.setattr(policy.one_click, "_emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(policy.time, "sleep", lambda _seconds: None)

    policy._wait_login_then_project_fixed(
        "job-2",
        "http://127.0.0.1:9444",
        policy.coproducao._PROJECT_URL,
        timeout_seconds=2,
    )

    assert opened == [policy.coproducao._PROJECT_URL]
