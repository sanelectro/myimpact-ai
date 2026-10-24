import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.services import evidence_discovery, source_connections
from app.services.demo_source_mocks import DEMO_SOURCE_RECORDS
from app.services.source_connections import SourceConnectionError


class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.request = None

    async def generate(self, request):
        self.request = request
        return SimpleNamespace(content=self.content)


def _candidate():
    return {
        "id": "github:org/repo#12",
        "source_type": "github",
        "source_id": "org/repo#12",
        "title": "Add service dashboards",
        "description": "Added dashboard panels and alert thresholds.",
        "source_url": "https://github.com/org/repo/pull/12",
        "captured_at": datetime(2026, 10, 20, tzinfo=UTC),
        "source_updated_at": None,
        "repository": "org/repo",
        "jira_keys": ["ENG-42"],
    }


def test_demo_personas_discover_github_and_jira_evidence(monkeypatch):
    monkeypatch.setattr(
        source_connections,
        "get_settings",
        lambda: SimpleNamespace(
            source_demo_mocks_enabled=True,
            app_env="development",
        ),
    )

    for user_id, persona in DEMO_SOURCE_RECORDS.items():
        github_candidates, jira_keys = evidence_discovery._fetch_github_candidates(
            session=None,
            user_id=user_id,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 23),
        )
        jira_candidates = evidence_discovery._fetch_jira_candidates(
            session=None,
            user_id=user_id,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 23),
            jira_keys=jira_keys,
        )

        assert len(github_candidates) == 1
        assert github_candidates[0]["title"] == persona["summary"]
        assert jira_keys == {persona["issue_key"]}
        assert len(jira_candidates) == 1
        assert jira_candidates[0]["source_id"] == persona["issue_key"]


def test_github_pull_request_candidates_extract_linked_jira_keys(monkeypatch):
    monkeypatch.setattr(
        evidence_discovery,
        "get_access_token",
        lambda *args: ("access-token", None),
    )

    def fake_source_api_get(url, *_args, **_kwargs):
        if url.endswith("/user"):
            return {"login": "test-user"}
        if url.endswith("/search/commits"):
            return {
                "items": [
                    {
                        "sha": "abc123",
                        "html_url": "https://github.com/acme/api/commit/abc123",
                        "repository": {"full_name": "acme/api"},
                        "commit": {
                            "message": "ENG-17 add health metrics",
                            "author": {"date": "2026-10-20T12:00:00Z"},
                        },
                    }
                ]
            }
        return [
            {
                "number": 17,
                "title": "ENG-18: Publish service health metrics",
                "body": "Adds dashboards for ENG-17 follow-up.",
                "html_url": "https://github.com/acme/api/pull/17",
                "created_at": "2026-10-20T12:30:00Z",
                "updated_at": "2026-10-20T13:00:00Z",
            }
        ]

    monkeypatch.setattr(evidence_discovery, "source_api_get", fake_source_api_get)

    candidates, jira_keys = evidence_discovery._fetch_github_candidates(
        session=None,
        user_id="user-1",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
    )

    assert candidates[0]["source_id"] == "acme/api#17"
    assert candidates[0]["source_url"] == "https://github.com/acme/api/pull/17"
    assert candidates[0]["jira_keys"] == ["ENG-17", "ENG-18"]
    assert jira_keys == {"ENG-17", "ENG-18"}


def test_jira_candidate_requires_done_status_and_in_range_resolution():
    connection = SimpleNamespace(external_base_url="https://example.atlassian.net")
    issue = {
        "key": "ENG-17",
        "fields": {
            "summary": "Publish service health metrics",
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Add key dashboards."}],
                    }
                ],
            },
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Story"},
            "resolutiondate": "2026-10-20T13:00:00Z",
            "updated": "2026-10-20T13:00:00Z",
        },
    }

    candidate = evidence_discovery._jira_issue_candidate(
        issue,
        connection,
        date(2026, 10, 1),
        date(2026, 10, 23),
    )
    issue["fields"]["status"]["statusCategory"]["key"] = "indeterminate"
    not_delivered = evidence_discovery._jira_issue_candidate(
        issue,
        connection,
        date(2026, 10, 1),
        date(2026, 10, 23),
    )

    assert candidate is not None
    assert candidate["source_url"] == "https://example.atlassian.net/browse/ENG-17"
    assert candidate["description"] == "Add key dashboards."
    assert not_delivered is None


def test_jira_fallback_search_uses_user_and_inclusive_date_range(monkeypatch):
    connection = SimpleNamespace(external_account_id="jira-cloud-id")
    monkeypatch.setattr(
        evidence_discovery,
        "get_access_token",
        lambda *args: ("access-token", connection),
    )
    calls = []

    def fake_post(url, token, body):
        calls.append((url, token, body))
        return {"issues": []}

    monkeypatch.setattr(evidence_discovery, "source_api_post", fake_post)

    assert evidence_discovery._fetch_jira_candidates(
        session=None,
        user_id="user-1",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
        jira_keys=set(),
    ) == []
    assert calls[0][2]["jql"] == (
        'assignee = currentUser() AND statusCategory = Done AND updated >= "2026-10-01" '
        'AND updated < "2026-10-24" ORDER BY updated DESC'
    )


@pytest.mark.asyncio
async def test_discovery_uses_milestone_context_and_keeps_source_provenance(monkeypatch):
    candidate = _candidate()
    fake_llm = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "id": candidate["id"],
                        "summary": "Added dashboards and alert thresholds.",
                        "relevance": "high",
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_github_candidates",
        lambda *args: ([candidate], {"ENG-42"}),
    )
    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_jira_candidates",
        lambda *args: [],
    )
    monkeypatch.setattr(evidence_discovery, "create_llm_service", lambda: fake_llm)

    results = await evidence_discovery.discover_evidence(
        session=None,
        user_id="user-1",
        goal_title="Improve platform reliability",
        goal_description="Increase observability and reduce incident duration.",
        milestone_title="Create service dashboards",
        milestone_description="Publish key latency and error-rate views.",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
        sources=["github"],
    )

    assert "milestone context" in fake_llm.request.prompt
    assert results[0]["source_url"] == candidate["source_url"]
    assert results[0]["source_id"] == candidate["source_id"]
    assert results[0]["summary"] == "Added dashboards and alert thresholds."
    assert results[0]["relevance"] == "high"


@pytest.mark.asyncio
async def test_discovery_rejects_ai_generated_source_ids(monkeypatch):
    candidate = _candidate()
    fake_llm = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "id": "github:invented/repo#99",
                        "summary": "This should not be accepted.",
                        "relevance": "high",
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_github_candidates",
        lambda *args: ([candidate], set()),
    )
    monkeypatch.setattr(evidence_discovery, "create_llm_service", lambda: fake_llm)

    with pytest.raises(SourceConnectionError, match="invalid evidence summary"):
        await evidence_discovery.discover_evidence(
            session=None,
            user_id="user-1",
            goal_title="Improve platform reliability",
            goal_description=None,
            milestone_title=None,
            milestone_description=None,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 23),
            sources=["github"],
        )
