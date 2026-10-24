import json
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.routes.document import get_document_service
from app.api.v1.goal_import import get_goal_import_service
from app.db.models.document import DocumentDB
from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.document import DocumentClassification, DocumentType
from app.models.llm import LLMResponse
from app.models.user import UserCreate
from app.services.document import DocumentService
from app.services.document_classification import DocumentClassificationService
from app.services.goal_import import GoalImportService
from app.services.user import UserService
from app.storage.local import LocalFileStorage


def _docx_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>2026 Platform Engineering team goal</w:t></w:r></w:p>
    <w:p><w:r><w:t>Reduce CI pipeline runtime from 20 minutes to 10 minutes by December 31, 2026.</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>""",
        )
    return buffer.getvalue()


class DeterministicGoalLLM:
    async def generate(self, _request):
        return LLMResponse(
            content=json.dumps(
                {
                    "goals": [
                        {
                            "title": "Reduce CI pipeline runtime",
                            "description": "Reduce the CI pipeline runtime from 20 minutes to 10 minutes.",
                            "scope": "team",
                            "start_date": "2026-01-01",
                            "end_date": "2026-12-31",
                            "confidence": 0.98,
                        }
                    ]
                }
            )
        )


@pytest.mark.integration
def test_upload_extract_review_and_approve_goal_from_document(tmp_path):
    session = SessionLocal()
    user_id = None
    document_id = None
    client = None
    storage = LocalFileStorage(tmp_path)
    classification_service = AsyncMock(spec=DocumentClassificationService)
    classification_service.classify.return_value = DocumentClassification(
        document_type=DocumentType.GOAL,
        confidence=1.0,
        reason="Contains a team goal.",
    )
    document_service = DocumentService(
        session,
        storage=storage,
        classification_service=classification_service,
    )

    dependencies = (get_document_service, get_goal_import_service)
    previous_overrides = {
        dependency: app.dependency_overrides.get(dependency)
        for dependency in dependencies
    }

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Goal Document Ingestion User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id
        app.dependency_overrides[get_document_service] = lambda: document_service
        app.dependency_overrides[get_goal_import_service] = lambda: GoalImportService(
            session,
            storage,
            DeterministicGoalLLM(),
        )
        client = TestClient(app)

        uploaded = client.post(
            "/api/v1/documents/import",
            data={"user_id": user_id},
            files={
                "file": (
                    "platform-goal.docx",
                    _docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        document = uploaded.json()
        document_id = document["id"]
        assert document["status"] == "processed"
        assert document["extracted_content_path"]
        assert storage.exists(document["storage_path"])
        assert storage.exists(document["extracted_content_path"])

        imported = client.post(
            "/api/v1/goals/import-from-document",
            params={"document_id": document_id, "user_id": user_id},
        )
        assert imported.status_code == 201, imported.text
        result = imported.json()
        assert result["skipped_duplicates"] == []
        assert len(result["imported_goals"]) == 1
        goal = result["imported_goals"][0]
        assert goal["status"] == "draft"
        assert goal["scope"] == "team"
        assert goal["source_document_id"] == document_id
        assert goal["start_date"] == "2026-01-01"
        assert goal["end_date"] == "2026-12-31"

        repeated_import = client.post(
            "/api/v1/goals/import-from-document",
            params={"document_id": document_id, "user_id": user_id},
        )
        assert repeated_import.status_code == 201
        assert [item["id"] for item in repeated_import.json()["imported_goals"]] == [
            goal["id"]
        ]

        edited = client.put(
            f"/api/v1/goals/{goal['id']}",
            params={"user_id": user_id},
            json={
                "title": "Reduce CI pipeline runtime to 10 minutes",
                "description": "Reviewed and corrected by the user.",
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["status"] == "draft"
        assert edited.json()["description"] == "Reviewed and corrected by the user."

        approved = client.post(
            f"/api/v1/goals/{goal['id']}/approve",
            params={"user_id": user_id},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        activated = client.post(
            f"/api/v1/goals/{goal['id']}/activate",
            params={"user_id": user_id},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["status"] == "active"
    finally:
        if client is not None:
            client.close()
        for dependency, previous in previous_overrides.items():
            if previous is None:
                app.dependency_overrides.pop(dependency, None)
            else:
                app.dependency_overrides[dependency] = previous

        if user_id is not None:
            session.execute(delete(GoalDB).where(GoalDB.user_id == user_id))
            session.execute(delete(DocumentDB).where(DocumentDB.user_id == user_id))
            session.execute(delete(UserDB).where(UserDB.id == user_id))
            session.commit()
        session.close()
