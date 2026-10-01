from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentType
from app.models.user import UserCreate
from app.services.document import DocumentService
from app.services.user import UserService
from app.storage.local import LocalFileStorage


def _docx_bytes(*paragraphs: str) -> bytes:
    xml_paragraphs = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        for text in paragraphs
    )

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        {xml_paragraphs}
        <w:sectPr/>
    </w:body>
</w:document>
"""

    relationships_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship
        Id="rId1"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
        Target="word/document.xml"
    />
</Relationships>
"""

    document_relationships_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>
"""

    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override
        PartName="/word/document.xml"
        ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    />
</Types>
"""

    buffer = BytesIO()

    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            content_types_xml,
        )
        archive.writestr(
            "_rels/.rels",
            relationships_xml,
        )
        archive.writestr(
            "word/document.xml",
            document_xml,
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            document_relationships_xml,
        )

    return buffer.getvalue()


@pytest.mark.integration
def test_document_service_extracts_docx_with_docling(tmp_path: Path):
    session = SessionLocal()
    user_id = None
    document_id = None
    storage = LocalFileStorage(tmp_path)

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Docling User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        service = DocumentService(
            session,
            storage=storage,
        )

        document = service.upload_document(
            user_id=user_id,
            document_type=DocumentType.ONE_TO_ONE,
            file_name="one-to-one.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            content=_docx_bytes(
                "Doing well on reliability initiatives.",
                "Take greater end-to-end ownership.",
            ),
        )
        document_id = document.id

        processed = service.process_document(document_id)

        assert processed.status.value == "processed"
        assert processed.extracted_content_path

        extracted_markdown = storage.read(
            processed.extracted_content_path
        ).decode("utf-8")

        assert "Doing well on reliability initiatives." in (
            extracted_markdown
        )
        assert "Take greater end-to-end ownership." in (
            extracted_markdown
        )

        stored = session.get(DocumentDB, document_id)

        assert stored is not None
        assert stored.status.value == "processed"
        assert stored.extracted_content_path == (
            processed.extracted_content_path
        )
        assert storage.exists(stored.extracted_content_path)

    finally:
        if document_id:
            session.execute(
                delete(DocumentDB).where(
                    DocumentDB.id == document_id
                )
            )

        if user_id:
            session.execute(
                delete(UserDB).where(
                    UserDB.id == user_id
                )
            )

        session.commit()
        session.close()
