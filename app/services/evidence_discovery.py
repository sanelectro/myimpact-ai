import json
import logging
import re
from datetime import UTC, date, datetime, timedelta

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
MAX_CANDIDATES_FOR_SUMMARY = 80
logger = logging.getLogger(__name__)


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


def _extract_jira_keys(*values: str | None) -> set[str]:
    return {
        match
        for value in values
        if value
        for match in JIRA_KEY_PATTERN.findall(value.upper())
    }


def _fetch_github_candidates(
    session: Session,
    user_id: str,
    start_date: date,
    end_date: date,
) -> tuple[list[dict], set[str]]:
    token, _ = get_access_token(session, user_id, "github")
    profile = source_api_get("https://api.github.com/user", token, "github")
    username = profile.get("login") if isinstance(profile, dict) else None
    if not isinstance(username, str) or not username:
        raise SourceConnectionError("GitHub did not return the connected user's login.")

    query = (
        f"author:{username} author-date:{start_date.isoformat()}..{end_date.isoformat()}"
    )
    search = source_api_get(
        "https://api.github.com/search/commits",
        token,
        "github",
        params={
            "q": query,
            "sort": "author-date",
            "order": "desc",
            "per_page": str(MAX_GITHUB_COMMITS),
        },
    )
    items = search.get("items", []) if isinstance(search, dict) else []
    logger.info("GitHub commit search returned %d record(s).", len(items))
    candidates: dict[str, dict] = {}
    jira_keys: set[str] = set()
    for commit in items:
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

        pull_requests = source_api_get(
            f"https://api.github.com/repos/{repo_name}/commits/{sha}/pulls",
            token,
            "github",
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
    resolved = fields.get("resolutiondate") or fields.get("updated")
    captured_at = _parse_source_datetime(resolved)
    if captured_at is None:
        return None
    if not start_date <= captured_at.date() <= end_date:
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
        "source_updated_at": _parse_source_datetime(fields.get("updated")),
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
        for key in sorted(jira_keys):
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
            "ORDER BY updated DESC"
        )
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
                "maxResults": 50,
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
    logger.info(
        "Evidence discovery started for sources=%s and date range %s..%s.",
        ",".join(sources),
        start_date,
        end_date,
    )
    candidates: list[dict] = []
    jira_keys: set[str] = set()
    if "github" in sources:
        github_candidates, jira_keys = _fetch_github_candidates(
            session, user_id, start_date, end_date
        )
        candidates.extend(github_candidates)
    if "jira" in sources:
        candidates.extend(
            _fetch_jira_candidates(
                session, user_id, start_date, end_date, jira_keys
            )
        )
    if not candidates:
        logger.info("Evidence discovery found no source candidates.")
        return []

    candidates = candidates[:MAX_CANDIDATES_FOR_SUMMARY]
    logger.info("Summarizing %d source candidate(s).", len(candidates))
    context_name = "milestone" if milestone_title else "goal"
    context = {
        "goal": {
            "title": goal_title,
            "description": goal_description or "",
        },
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
        "('high', 'medium', or 'low'). Do not invent details, impact, business outcomes, "
        "or records. Do not imply that activity alone proves goal completion. Include "
        "only relevant source records; an empty array is valid. "
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

    by_id = {item["id"]: item for item in candidates}
    summarized = []
    seen_ids: set[str] = set()
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
        seen_ids.add(summary["id"])
        summarized.append(
            {
                **source,
                "summary": text.strip(),
                "relevance": relevance,
            }
        )
    logger.info(
        "Evidence summary retained %d of %d source candidate(s).",
        len(summarized),
        len(candidates),
    )
    return summarized
