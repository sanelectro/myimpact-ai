from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentScopeType
from app.repositories.document import DocumentRepository


def test_get_by_scope():
    session = MagicMock(spec=Session)
    document = MagicMock(spec=DocumentDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = [document]

    repository = DocumentRepository(session)

    result = repository.get_by_scope(
        DocumentScopeType.ROLE,
        "lead_engineer",
    )

    assert result == [document]
    session.query.assert_called_once_with(DocumentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
