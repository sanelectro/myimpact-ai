import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

from sqlalchemy.orm import Session

from app.models.llm import LLMRequest
from app.services.llm.factory import create_llm_service
from app.services.source_connections import (
    LocalSourceConnection,
    SourceConnectionDB,
    SourceConnectionError,
    get_access_token,
    source_api_get,
    source_api_post,
)


JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
MAX_GITHUB_COMMITS = 50
MAX_GITHUB_PULL_REQUEST_LOOKUPS = 50
MAX_JIRA_RESULTS = 50
MAX_CANDIDATES_FOR_SUMMARY = 80
CRITERION_SEARCH_TOKEN_LIMIT = 8
CRITERION_SEARCH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "complete", "completed",
    "completion", "criterion", "demonstrate", "for", "from", "goal", "in",
    "into", "is", "of", "on", "or", "the", "through", "to", "using", "with",
}
logger = logging.getLogger(__name__)


class CriterionSearchContext(TypedDict):
    criterion_id: str
    definition: dict[str, object]
    search_text: str


def _adf_to_text(node) -> str:
    if isinstance(node, list):
        return "\n".join(part for part in (_adf_to_text(item) for item in node) if part)
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text", ""))
    parts = [
        text for text in (_adf_to_text(item) for item in node.get("content", [])) if text
    ]
    separator = "\n" if node.get("type") in {"paragraph", "heading"} else " "
    return separator.join(parts).strip()


def _parse_source_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _candidate_event_at(candidate: dict) -> datetime | None:
    timestamps = [
        value
        for value in (
            candidate.get("captured_at"),
            candidate.get("source_updated_at"),
        )
        if isinstance(value, datetime)
    ]
    return max((_to_utc(value) for value in timestamps), default=None)


def _extract_jira_keys(*values: str | None) -> set[str]:
    return {
        match
        for value in values
        if value
        for match in JIRA_KEY_PATTERN.findall(value.upper())
    }


def _criterion_search_phrases(
    criteria: list[CriterionSearchContext] | None,
) -> list[str]:
    phrases: list[str] = []
    for criterion in criteria or []:
        tokens = re.findall(r"[A-Za-z0-9]+", criterion["search_text"].casefold())
        selected: list[str] = []
        for token in tokens:
            if token in CRITERION_SEARCH_STOP_WORDS or token in selected:
                continue
            selected.append(token)
            if len(selected) == CRITERION_SEARCH_TOKEN_LIMIT:
                break
        if selected:
            phrases.append(" ".join(selected))
    return phrases


def _fetch_github_candidates(
    session: Session,
    user_id: str,
    start_date: date,
    end_date: date,
    max_commits: int = MAX_GITHUB_COMMITS,
    max_pull_request_lookups: int = MAX_GITHUB_PULL_REQUEST_LOOKUPS,
    criterion_phrases: list[str] | None = None,
) -> tuple[list[dict], set[str]]:
    token, _ = get_access_token(session, user_id, "github")
    profile = source_api_get("https://api.github.com/user", token, "github")
    username = profile.get("login") if isinstance(profile, dict) else None
    if not isinstance(username, str) or not username:
        raise SourceConnectionError("GitHub did not return the connected user's login.")

    query = f"author:{username} author-date:{start_date.isoformat()}..{end_date.isoformat()}"
    if criterion_phrases:
        query += " (" + " OR ".join(f'"{phrase}"' for phrase in criterion_phrases) + ")"
    search = source_api_get(
        "https://api.github.com/search/commits",
        token,
        "github",
        params={
            "q": query,
            "sort": "author-date",
            "order": "desc",
            "per_page": str(max_commits),
        },
    )
    items = search.get("items", []) if isinstance(search, dict) else []
    if not isinstance(items, list):
        items = []
    logger.info("GitHub commit search returned %d record(s).", len(items))
    candidates: dict[str, dict] = {}
    jira_keys: set[str] = set()
    for index, commit in enumerate(items[:max_commits]):
        if not isinstance(commit, dict):
            continue
        repository = commit.get("repository") or {}
        repo_name = repository.get("full_name")
        sha = commit.get("sha")
        if not isinstance(repo_name, str) or not isinstance(sha, str):
            continue
        commit_data = commit.get("commit") or {}
        message = commit_data.get("message") or ""
        author = commit_data.get("author") or {}
        captured_at = _parse_source_datetime(author.get("date"))
        if captured_at is None:
            continue
        commit_url = commit.get("html_url")
        commit_keys = _extract_jira_keys(message)
        jira_keys.update(commit_keys)

        pull_requests = (
            source_api_get(
                f"https://api.github.com/repos/{repo_name}/commits/{sha}/pulls",
                token,
                "github",
            )
            if index < max_pull_request_lookups
            else []
        )
        if isinstance(pull_requests, list) and pull_requests:
            for pull_request in pull_requests:
                if not isinstance(pull_request, dict):
                    continue
                number = pull_request.get("number")
                title = pull_request.get("title")
                source_url = pull_request.get("html_url")
                if not isinstance(number, int) or not isinstance(title, str):
                    continue
                body = pull_request.get("body") or ""
                pr_keys = _extract_jira_keys(title, body)
                jira_keys.update(pr_keys)
                source_id = f"{repo_name}#{number}"
                pr_date = _parse_source_datetime(
                    pull_request.get("merged_at") or pull_request.get("created_at")
                )
                if pr_date is None or not start_date <= pr_date.date() <= end_date:
                    pr_date = captured_at
                candidates[f"github:{source_id}"] = {
                    "id": f"github:{source_id}",
                    "source_type": "github",
                    "source_id": source_id,
                    "title": title,
                    "description": body or message,
                    "source_url": source_url,
                    "captured_at": pr_date,
                    "source_updated_at": _parse_source_datetime(
                        pull_request.get("updated_at")
                    ),
                    "repository": repo_name,
                    "jira_keys": sorted(pr_keys | commit_keys),
                }
        else:
            source_id = sha
            candidates[f"github:{sha}"] = {
                "id": f"github:{sha}",
                "source_type": "github",
                "source_id": source_id,
                "title": message.splitlines()[0][:500] or f"Commit {sha[:7]}",
                "description": message,
                "source_url": commit_url,
                "captured_at": captured_at,
                "source_updated_at": _parse_source_datetime(commit_data.get("committer", {}).get("date"))
                or captured_at,
                "repository": repo_name,
                "jira_keys": sorted(commit_keys),
            }
    logger.info(
        "GitHub discovery produced %d candidate(s) from %d search result(s).",
        len(candidates),
        len(items),
    )
    return list(candidates.values()), jira_keys


def _jira_issue_candidate(
    issue: dict,
    connection: SourceConnectionDB,
    start_date: date,
    end_date: date,
) -> dict | None:
    fields = issue.get("fields") or {}
    issue_type = (fields.get("issuetype") or {}).get("name", "")
    if issue_type and issue_type.casefold() not in {"story", "task", "bug", "epic"}:
        return None
    status = fields.get("status") or {}
    status_category = status.get("statusCategory") or {}
    if status_category.get("key") != "done":
        return None
    key = issue.get("key")
    title = fields.get("summary")
    if not isinstance(key, str) or not isinstance(title, str):
        return None
    source_updated_at = _parse_source_datetime(fields.get("updated"))
    captured_at = (
        _parse_source_datetime(fields.get("resolutiondate")) or source_updated_at
    )
    if captured_at is None and source_updated_at is None:
        return None
    in_range = any(
        timestamp is not None and start_date <= timestamp.date() <= end_date
        for timestamp in (captured_at, source_updated_at)
    )
    if not in_range:
        return None
    description = _adf_to_text(fields.get("description"))
    base_url = (connection.external_base_url or "").rstrip("/")
    source_url = f"{base_url}/browse/{key}" if base_url else None
    return {
        "id": f"jira:{key}",
        "source_type": "jira",
        "source_id": key,
        "title": title,
        "description": description,
        "source_url": source_url,
        "captured_at": captured_at,
        "source_updated_at": source_updated_at,
        "status": status.get("name", ""),
        "issue_type": issue_type,
        "jira_keys": [key],
    }


def _fetch_jira_candidates(
    session: Session,
    user_id: str,
    start_date: date,
    end_date: date,
    jira_keys: set[str],
    max_results: int = MAX_JIRA_RESULTS,
    criterion_phrases: list[str] | None = None,
) -> list[dict]:
    token, connection = get_access_token(session, user_id, "jira")
    local_jira_email = (
        connection.jira_email
        if isinstance(connection, LocalSourceConnection)
        else None
    )
    base_url = (
        connection.external_base_url.rstrip("/")
        if local_jira_email and connection.external_base_url
        else f"https://api.atlassian.com/ex/jira/{connection.external_account_id}"
    )
    issues: list[dict] = []
    if jira_keys:
        for key in sorted(jira_keys)[:max_results]:
            issue = source_api_get(
                f"{base_url}/rest/api/3/issue/{key}",
                token,
                "jira",
                params={
                    "fields": "summary,description,status,assignee,updated,created,resolutiondate,issuetype"
                },
                **({"jira_email": local_jira_email} if local_jira_email else {}),
            )
            if isinstance(issue, dict):
                issues.append(issue)
    else:
        jql = (
            "assignee = currentUser() AND statusCategory = Done "
            f'AND updated >= "{start_date.isoformat()}" '
            f'AND updated < "{(end_date + timedelta(days=1)).isoformat()}" '
        )
        if criterion_phrases:
            criterion_query = " OR ".join(
                f'text ~ "{phrase}"' for phrase in criterion_phrases
            )
            jql += f"AND ({criterion_query}) "
        jql += "ORDER BY updated DESC"
        search = source_api_post(
            f"{base_url}/rest/api/3/search/jql",
            token,
            {
                "jql": jql,
                "fields": [
                    "summary",
                    "description",
                    "status",
                    "assignee",
                    "updated",
                    "created",
                    "resolutiondate",
                    "issuetype",
                ],
                "maxResults": max_results,
            },
            **({"jira_email": local_jira_email} if local_jira_email else {}),
        )
        if isinstance(search, dict):
            issues.extend(search.get("issues", []))

    candidates = [
        candidate
        for issue in issues
        if (candidate := _jira_issue_candidate(issue, connection, start_date, end_date))
    ]
    logger.info(
        "Jira discovery produced %d candidate(s) from %d issue(s).",
        len(candidates),
        len(issues),
    )
    return candidates


async def discover_evidence(
    session: Session,
    user_id: str,
    goal_title: str,
    goal_description: str | None,
    milestone_title: str | None,
    milestone_description: str | None,
    start_date: date,
    end_date: date,
    sources: list[str],
) -> list[dict]:
    return await discover_evidence_bounded(
        session,
        user_id,
        goal_title,
        goal_description,
        milestone_title,
        milestone_description,
        start_date,
        end_date,
        sources,
    )


async def discover_evidence_bounded(
    session: Session,
    user_id: str,
    goal_title: str,
    goal_description: str | None,
    milestone_title: str | None,
    milestone_description: str | None,
    start_date: date,
    end_date: date,
    sources: list[str],
    *,
    jira_keys: set[str] | None = None,
    max_github_commits: int = MAX_GITHUB_COMMITS,
    max_github_pull_request_lookups: int = MAX_GITHUB_PULL_REQUEST_LOOKUPS,
    max_jira_results: int = MAX_JIRA_RESULTS,
    max_candidates: int = MAX_CANDIDATES_FOR_SUMMARY,
    after: datetime | None = None,
    criteria: list[CriterionSearchContext] | None = None,
) -> list[dict]:
    logger.info(
        "Evidence discovery started for sources=%s and date range %s..%s.",
        ",".join(sources),
        start_date,
        end_date,
    )
    candidates: list[dict] = []
    criterion_phrases = _criterion_search_phrases(criteria)
    related_jira_keys = set(jira_keys or ())
    if "github" in sources:
        github_candidates, discovered_jira_keys = _fetch_github_candidates(
            session,
            user_id,
            start_date,
            end_date,
            max_github_commits,
            max_github_pull_request_lookups,
            criterion_phrases,
        )
        candidates.extend(github_candidates)
        related_jira_keys.update(discovered_jira_keys)
    if "jira" in sources:
        candidates.extend(
            _fetch_jira_candidates(
                session,
                user_id,
                start_date,
                end_date,
                related_jira_keys,
                max_jira_results,
                criterion_phrases,
            )
        )
    if after is not None:
        watermark = _to_utc(after)
        candidates = [
            candidate
            for candidate in candidates
            if (event_at := _candidate_event_at(candidate)) is not None
            and event_at > watermark
        ]
    if not candidates:
        logger.info("Evidence discovery found no source candidates.")
        return []

    candidates = candidates[:max_candidates]
    logger.info("Summarizing %d source candidate(s).", len(candidates))
    context_name = "milestone" if milestone_title else "goal"
    context = {
        "goal": {
            "title": goal_title,
            "description": goal_description or "",
        },
        "approved_criteria": criteria or [],
        "milestone": (
            {
                "title": milestone_title,
                "description": milestone_description or "",
            }
            if milestone_title
            else None
        ),
    }
    source_records = [
        {
            "id": item["id"],
            "source": item["source_type"],
            "title": item["title"],
            "description": str(item["description"] or "")[:2500],
            "repository": item.get("repository"),
            "status": item.get("status"),
            "issue_type": item.get("issue_type"),
            "jira_keys": item.get("jira_keys", []),
        }
        for item in candidates
    ]
    prompt = (
        "You help a user review source records as possible evidence for their work goal. "
        f"Use the {context_name} context to choose records that are meaningfully related. "
        "Return a JSON object with an 'items' array. Each item must contain the exact "
        "input id, a concise factual summary (1-3 sentences), and a relevance value "
        "('high', 'medium', or 'low'). "
        + (
            "For each item, include criterion_ids containing only approved criterion "
            "IDs the record materially relates to, including potentially contradictory "
            "evidence. Also return criterion_sufficiency with exactly one entry per "
            "approved criterion: criterion_id and sufficient (boolean). "
            "Sufficient means the retrieved records provide enough relevant context to "
            "attempt an assessment; it does not mean the criterion is met. "
            if criteria
            else ""
        )
        + "Do not invent details, impact, business outcomes, or records. Do not imply "
        "that activity alone proves goal completion. Include only relevant source "
        "records; an empty array is valid. "
        f"Context: {json.dumps(context, ensure_ascii=False)} "
        f"Source records: {json.dumps(source_records, ensure_ascii=False)}"
    )
    try:
        response = await create_llm_service().generate(
            LLMRequest(
                prompt=prompt,
                response_format={"type": "json_object"},
            )
        )
    except Exception as exc:
        logger.exception("AI evidence summarization failed.")
        raise SourceConnectionError(
            "AI evidence summarization failed. Please try again."
        ) from exc
    try:
        result = json.loads(response.content)
        summaries = result.get("items")
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        raise SourceConnectionError(
            "AI could not create a valid evidence summary. Please try again."
        ) from exc
    if not isinstance(summaries, list):
        raise SourceConnectionError(
            "AI returned an invalid evidence summary. Please try again."
        )

    allowed_criterion_ids = {
        criterion["criterion_id"] for criterion in criteria or []
    }
    criterion_sufficiency: dict[str, bool] = {}
    if criteria:
        sufficiency_items = result.get("criterion_sufficiency")
        if not isinstance(sufficiency_items, list):
            raise SourceConnectionError(
                "AI returned an invalid criterion retrieval assessment. Please try again."
            )
        for item in sufficiency_items:
            if (
                not isinstance(item, dict)
                or item.get("criterion_id") not in allowed_criterion_ids
                or not isinstance(item.get("sufficient"), bool)
                or item["criterion_id"] in criterion_sufficiency
            ):
                raise SourceConnectionError(
                    "AI returned an invalid criterion retrieval assessment. Please try again."
                )
            criterion_sufficiency[item["criterion_id"]] = item["sufficient"]
        if set(criterion_sufficiency) != allowed_criterion_ids:
            raise SourceConnectionError(
                "AI returned an incomplete criterion retrieval assessment. Please try again."
            )

    by_id = {item["id"]: item for item in candidates}
    summarized = []
    seen_ids: set[str] = set()
    matched_criterion_ids: set[str] = set()
    for summary in summaries:
        if not isinstance(summary, dict):
            raise SourceConnectionError(
                "AI returned an invalid evidence summary. Please try again."
            )
        source = by_id.get(summary.get("id"))
        text = summary.get("summary")
        relevance = summary.get("relevance")
        if (
            source is None
            or not isinstance(text, str)
            or not text.strip()
            or relevance not in {"high", "medium", "low"}
            or summary.get("id") in seen_ids
        ):
            raise SourceConnectionError(
                "AI returned an invalid evidence summary. Please try again."
            )
        criterion_ids: list[str] = []
        if criteria:
            raw_criterion_ids = summary.get("criterion_ids")
            if (
                not isinstance(raw_criterion_ids, list)
                or any(
                    not isinstance(criterion_id, str)
                    or criterion_id not in allowed_criterion_ids
                    for criterion_id in raw_criterion_ids
                )
                or len(raw_criterion_ids) != len(set(raw_criterion_ids))
            ):
                raise SourceConnectionError(
                    "AI returned an invalid criterion evidence reference. Please try again."
                )
            criterion_ids = raw_criterion_ids
            matched_criterion_ids.update(criterion_ids)
        seen_ids.add(summary["id"])
        if not criteria or criterion_ids:
            summarized.append(
                {
                    **source,
                    "summary": text.strip(),
                    "relevance": relevance,
                    **(
                        {
                            "criterion_ids": criterion_ids,
                            "criterion_sufficiency": criterion_sufficiency,
                        }
                        if criteria
                        else {}
                    ),
                }
            )
    if any(
        sufficient and criterion_id not in matched_criterion_ids
        for criterion_id, sufficient in criterion_sufficiency.items()
    ):
        raise SourceConnectionError(
            "AI marked criterion retrieval sufficient without relevant source records. Please try again."
        )
    logger.info(
        "Evidence summary retained %d of %d source candidate(s).",
        len(summarized),
        len(candidates),
    )
    return summarized
