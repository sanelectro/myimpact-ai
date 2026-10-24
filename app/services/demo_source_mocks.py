import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

_DEMO_DATA_PATH = Path(__file__).resolve().parents[2] / "demo-data" / "demo_personas.json"
with _DEMO_DATA_PATH.open(encoding="utf-8") as demo_data_file:
    _DEMO_DATA = json.load(demo_data_file)

DEMO_SOURCE_RECORDS = {
    persona["user_id"]: persona for persona in _DEMO_DATA["personas"]
}
_CAPTURED_AT = _DEMO_DATA["captured_at"]


def _record_for_token(access_token: str, provider: str) -> dict | None:
    prefix = f"myimpact-demo-mock:{provider}:"
    if not access_token.startswith(prefix):
        raise ValueError("Demo mock token does not match the requested provider.")
    user_id = access_token[len(prefix) :]
    persona = DEMO_SOURCE_RECORDS.get(user_id)
    if persona is None:
        return None
    return {
        **persona,
        "login": f"demo-{persona['slug']}",
        "repository": f"myimpact-demo/{persona['slug']}-growth",
        "sha": hashlib.sha1(user_id.encode("utf-8")).hexdigest(),
    }


def _issue(record: dict) -> dict:
    return {
        "key": record["issue_key"],
        "fields": {
            "summary": record["summary"],
            "description": record["evidence_description"],
            "status": {
                "name": "Done",
                "statusCategory": {"key": "done"},
            },
            "issuetype": {"name": "Story"},
            "resolutiondate": _CAPTURED_AT,
            "updated": _CAPTURED_AT,
        },
    }


def mock_source_response(
    method: str,
    url: str,
    access_token: str,
    provider: str,
    *,
    params: dict[str, str] | None = None,
    body: dict | None = None,
) -> dict | list:
    record = _record_for_token(access_token, provider)
    path = urlparse(url).path

    if provider == "github":
        if path == "/user":
            return {"login": record["login"] if record else "demo-empty"}
        if path == "/search/commits":
            if record is None or not _date_in_query_range(params):
                return {"items": []}
            return {
                "items": [
                    {
                        "sha": record["sha"],
                        "html_url": None,
                        "repository": {"full_name": record["repository"]},
                        "commit": {
                            "message": f"{record['issue_key']}: {record['summary']}",
                            "author": {"date": _CAPTURED_AT},
                            "committer": {"date": _CAPTURED_AT},
                        },
                    }
                ]
            }
        if record and path == (
            f"/repos/{record['repository']}/commits/{record['sha']}/pulls"
        ):
            pull_number = int(record["issue_key"].rsplit("-", 1)[1])
            return [
                {
                    "number": pull_number,
                    "title": record["summary"],
                    "body": record["evidence_description"],
                    "html_url": None,
                    "merged_at": _CAPTURED_AT,
                    "created_at": _CAPTURED_AT,
                    "updated_at": _CAPTURED_AT,
                }
            ]
        return {}

    if provider == "jira":
        if method == "GET" and record and path.endswith(
            f"/issue/{record['issue_key']}"
        ):
            return _issue(record)
        if method == "POST" and path.endswith("/search/jql"):
            return {"issues": [_issue(record)] if record else []}
        return {}

    raise ValueError("Unsupported demo mock provider.")


def _date_in_query_range(params: dict[str, str] | None) -> bool:
    query = (params or {}).get("q", "")
    match = re.search(
        r"author-date:(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})",
        query,
    )
    if match is None:
        return True
    start_date, end_date = (date.fromisoformat(value) for value in match.groups())
    captured_date = date.fromisoformat(_CAPTURED_AT[:10])
    return start_date <= captured_date <= end_date
