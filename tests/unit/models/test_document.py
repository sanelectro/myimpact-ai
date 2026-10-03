import pytest
from pydantic import ValidationError

from app.models.document import (
    DocumentCreate,
    DocumentScopeType,
    DocumentType,
)


def test_employee_document_defaults_scope_to_user():
    document = DocumentCreate(
        user_id="user-1",
        document_type=DocumentType.GOAL,
        file_name="goals.pdf",
        content_type="application/pdf",
        storage_path="documents/user-1/goals.pdf",
    )

    assert document.scope_type == DocumentScopeType.EMPLOYEE
    assert document.scope_id == "user-1"


def test_employee_document_rejects_different_scope_id():
    with pytest.raises(
        ValidationError,
        match="scope_id must match user_id",
    ):
        DocumentCreate(
            user_id="user-1",
            document_type=DocumentType.GOAL,
            file_name="goals.pdf",
            content_type="application/pdf",
            storage_path="documents/user-1/goals.pdf",
            scope_id="user-2",
        )


def test_role_document_requires_scope_id():
    with pytest.raises(
        ValidationError,
        match="Role documents require a scope_id",
    ):
        DocumentCreate(
            user_id="admin-1",
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.ROLE,
            file_name="lead-engineer-role.pdf",
            content_type="application/pdf",
            storage_path="documents/lead-engineer-role.pdf",
        )


def test_global_document_does_not_have_scope_id():
    document = DocumentCreate(
        user_id="admin-1",
        document_type=DocumentType.ROLE,
        scope_type=DocumentScopeType.GLOBAL,
        file_name="company-expectations.pdf",
        content_type="application/pdf",
        storage_path="documents/company-expectations.pdf",
    )

    assert document.scope_type == DocumentScopeType.GLOBAL
    assert document.scope_id is None


def test_global_document_rejects_scope_id():
    with pytest.raises(
        ValidationError,
        match="Global documents must not have a scope_id",
    ):
        DocumentCreate(
            user_id="admin-1",
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.GLOBAL,
            scope_id="lead-engineer",
            file_name="company-expectations.pdf",
            content_type="application/pdf",
            storage_path="documents/company-expectations.pdf",
        )
