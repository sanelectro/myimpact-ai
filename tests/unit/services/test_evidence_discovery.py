import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

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


def _criterion_contexts():
    return [
        {
            "criterion_id": "criterion-canary",
            "definition": {
                "description": "Reduce failed deployments",
                "completion_conditions": "Production canary validation is enabled.",
            },
            "search_text": "Reduce failed deployments through safer release checks",
        },
        {
            "criterion_id": "criterion-dashboard",
            "definition": {
                "description": "Publish service reliability dashboards",
                "completion_conditions": "Dashboards are available to on-call engineers.",
            },
            "search_text": "Service dashboards alert thresholds",
        },
    ]


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


@pytest.mark.asyncio
async def test_discovery_searches_for_approved_criterion_terms_with_existing_caps(monkeypatch):
    github_queries = []
    jira_queries = []
    connection = SimpleNamespace(
        jira_email=None,
        external_base_url=None,
        external_account_id="jira-account",
    )

    monkeypatch.setattr(
        evidence_discovery,
        "get_access_token",
        lambda _session, _user, provider: (
            "access-token",
            connection if provider == "jira" else None,
        ),
    )

    def fake_source_api_get(url, *_args, **kwargs):
        if url.endswith("/user"):
            return {"login": "test-user"}
        if url.endswith("/search/commits"):
            github_queries.append(kwargs["params"]["q"])
            return {"items": []}
        raise AssertionError(f"Unexpected GitHub request: {url}")

    def fake_source_api_post(_url, _token, payload, *_args, **_kwargs):
        jira_queries.append(payload["jql"])
        return {"issues": []}

    monkeypatch.setattr(evidence_discovery, "source_api_get", fake_source_api_get)
    monkeypatch.setattr(evidence_discovery, "source_api_post", fake_source_api_post)

    results = await evidence_discovery.discover_evidence_bounded(
        session=None,
        user_id="user-1",
        goal_title="Improve reliability",
        goal_description=None,
        milestone_title=None,
        milestone_description=None,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
        sources=["github", "jira"],
        max_github_commits=10,
        max_github_pull_request_lookups=5,
        max_jira_results=10,
        max_candidates=20,
        criteria=_criterion_contexts(),
    )

    assert results == []
    assert len(github_queries) == 1
    assert '"reduce failed deployments safer release checks"' in github_queries[0]
    assert '"service dashboards alert thresholds"' in github_queries[0]
    assert len(jira_queries) == 1
    assert 'text ~ "reduce failed deployments safer release checks"' in jira_queries[0]
    assert 'text ~ "service dashboards alert thresholds"' in jira_queries[0]
    assert "statusCategory = Done" in jira_queries[0]


@pytest.mark.asyncio
async def test_bounded_discovery_matches_candidates_and_checks_retrieval_sufficiency(
    monkeypatch,
):
    candidate = _candidate()
    contexts = _criterion_contexts()
    fake_llm = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "id": candidate["id"],
                        "summary": "The pull request added service dashboards.",
                        "relevance": "high",
                        "criterion_ids": ["criterion-dashboard"],
                    }
                ],
                "criterion_sufficiency": [
                    {
                        "criterion_id": "criterion-canary",
                        "sufficient": False,
                    },
                    {
                        "criterion_id": "criterion-dashboard",
                        "sufficient": True,
                    },
                ],
            }
        )
    )
    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_github_candidates",
        lambda *_args: ([candidate], set()),
    )
    monkeypatch.setattr(evidence_discovery, "create_llm_service", lambda: fake_llm)

    results = await evidence_discovery.discover_evidence_bounded(
        session=None,
        user_id="user-1",
        goal_title="Improve reliability",
        goal_description=None,
        milestone_title=None,
        milestone_description=None,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
        sources=["github"],
        criteria=contexts,
    )

    assert "approved_criteria" in fake_llm.request.prompt
    assert results[0]["criterion_ids"] == ["criterion-dashboard"]
    assert results[0]["criterion_sufficiency"] == {
        "criterion-canary": False,
        "criterion-dashboard": True,
    }


@pytest.mark.asyncio
async def test_bounded_discovery_rejects_unknown_criterion_matches(monkeypatch):
    candidate = _candidate()
    fake_llm = FakeLLM(
        json.dumps(
            {
                "items": [
                    {
                        "id": candidate["id"],
                        "summary": "The pull request added service dashboards.",
                        "relevance": "high",
                        "criterion_ids": ["criterion-not-approved"],
                    }
                ],
                "criterion_sufficiency": [
                    {
                        "criterion_id": "criterion-canary",
                        "sufficient": False,
                    },
                    {
                        "criterion_id": "criterion-dashboard",
                        "sufficient": False,
                    },
                ],
            }
        )
    )
    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_github_candidates",
        lambda *_args: ([candidate], set()),
    )
    monkeypatch.setattr(evidence_discovery, "create_llm_service", lambda: fake_llm)

    with pytest.raises(SourceConnectionError, match="criterion evidence reference"):
        await evidence_discovery.discover_evidence_bounded(
            session=None,
            user_id="user-1",
            goal_title="Improve reliability",
            goal_description=None,
            milestone_title=None,
            milestone_description=None,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 23),
            sources=["github"],
            criteria=_criterion_contexts(),
        )


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


def test_source_discovery_applies_commit_and_pull_request_lookup_limits(monkeypatch):
    monkeypatch.setattr(
        evidence_discovery,
        "get_access_token",
        lambda *_args: ("access-token", None),
    )
    calls = []
    commit_items = [
        {
            "sha": f"sha-{index}",
            "html_url": f"https://github.com/acme/api/commit/sha-{index}",
            "repository": {"full_name": "acme/api"},
            "commit": {
                "message": f"Update service component {index}",
                "author": {"date": "2026-10-20T12:00:00Z"},
            },
        }
        for index in range(12)
    ]

    def fake_source_api_get(url, *_args, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/user"):
            return {"login": "test-user"}
        if url.endswith("/search/commits"):
            return {"items": commit_items}
        return []

    monkeypatch.setattr(evidence_discovery, "source_api_get", fake_source_api_get)

    candidates, _jira_keys = evidence_discovery._fetch_github_candidates(
        session=None,
        user_id="user-1",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
        max_commits=10,
        max_pull_request_lookups=5,
    )

    search_call = next(call for call in calls if call[0].endswith("/search/commits"))
    pull_calls = [call for call in calls if call[0].endswith("/pulls")]
    assert search_call[1]["params"]["per_page"] == "10"
    assert len(pull_calls) == 5
    assert len(candidates) == 10


def test_jira_linked_issue_retrieval_respects_result_limit(monkeypatch):
    connection = SimpleNamespace(external_account_id="jira-cloud-id")
    monkeypatch.setattr(
        evidence_discovery,
        "get_access_token",
        lambda *_args: ("access-token", connection),
    )
    calls = []

    def fake_source_api_get(url, *_args, **_kwargs):
        calls.append(url)
        return {}

    monkeypatch.setattr(evidence_discovery, "source_api_get", fake_source_api_get)

    evidence_discovery._fetch_jira_candidates(
        session=None,
        user_id="user-1",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 23),
        jira_keys={f"ENG-{index}" for index in range(20)},
        max_results=10,
    )

    assert len(calls) == 10


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
            "resolutiondate": "2026-09-20T13:00:00Z",
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
    assert candidate["captured_at"].date() == date(2026, 9, 20)
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
async def test_bounded_discovery_caps_candidates_sent_for_summarization(monkeypatch):
    candidates = [
        {
            **_candidate(),
            "id": f"github:org/repo#{number}",
            "source_id": f"org/repo#{number}",
            "title": f"Candidate {number}",
        }
        for number in range(25)
    ]

    class BoundedLLM:
        request = None

        async def generate(self, request):
            self.request = request
            source_records = json.loads(request.prompt.rsplit("Source records: ", 1)[1])
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "items": [
                            {
                                "id": record["id"],
                                "summary": "The source record is related to the goal.",
                                "relevance": "medium",
                            }
                            for record in source_records
                        ]
                    }
                )
            )

    fake_llm = BoundedLLM()
    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_github_candidates",
        lambda *args: (candidates, set()),
    )
    monkeypatch.setattr(evidence_discovery, "create_llm_service", lambda: fake_llm)

    with Session() as session:
        results = await evidence_discovery.discover_evidence_bounded(
            session=session,
            user_id="user-1",
            goal_title="Improve platform reliability",
            goal_description=None,
            milestone_title=None,
            milestone_description=None,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 23),
            sources=["github"],
            jira_keys=None,
            max_github_commits=10,
            max_github_pull_request_lookups=5,
            max_jira_results=10,
            max_candidates=20,
        )

    source_records = json.loads(fake_llm.request.prompt.rsplit("Source records: ", 1)[1])
    assert len(source_records) == 20
    assert len(results) == 20


@pytest.mark.asyncio
async def test_bounded_discovery_excludes_candidates_at_or_before_watermark(monkeypatch):
    now = datetime.now(UTC)
    watermark = now - timedelta(hours=1)
    candidates = [
        {
            **_candidate(),
            "id": "github:org/repo#old",
            "source_id": "org/repo#old",
            "captured_at": now - timedelta(hours=3),
            "source_updated_at": now - timedelta(hours=2),
        },
        {
            **_candidate(),
            "id": "github:org/repo#equal",
            "source_id": "org/repo#equal",
            "captured_at": watermark,
            "source_updated_at": None,
        },
        {
            **_candidate(),
            "id": "github:org/repo#new",
            "source_id": "org/repo#new",
            "captured_at": now,
            "source_updated_at": None,
        },
        {
            **_candidate(),
            "id": "github:org/repo#updated",
            "source_id": "org/repo#updated",
            "captured_at": now - timedelta(days=30),
            "source_updated_at": now - timedelta(minutes=30),
        },
    ]

    class WatermarkLLM:
        async def generate(self, request):
            records = json.loads(request.prompt.rsplit("Source records: ", 1)[1])
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "items": [
                            {
                                "id": record["id"],
                                "summary": "The source record is related to the goal.",
                                "relevance": "medium",
                            }
                            for record in records
                        ]
                    }
                )
            )

    monkeypatch.setattr(
        evidence_discovery,
        "_fetch_github_candidates",
        lambda *args: (candidates, set()),
    )
    monkeypatch.setattr(
        evidence_discovery,
        "create_llm_service",
        lambda: WatermarkLLM(),
    )

    results = await evidence_discovery.discover_evidence_bounded(
        session=None,
        user_id="user-1",
        goal_title="Improve platform reliability",
        goal_description=None,
        milestone_title=None,
        milestone_description=None,
        start_date=(now - timedelta(days=365)).date(),
        end_date=now.date(),
        sources=["github"],
        after=watermark,
    )

    assert {result["source_id"] for result in results} == {
        "org/repo#new",
        "org/repo#updated",
    }


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
