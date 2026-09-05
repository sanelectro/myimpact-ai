from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app


client = TestClient(app)


@pytest.mark.integration
def test_create_user():
    email = f"{uuid4()}@example.com"

    response = client.post(
        "/users",
        json={
            "name": "API Integration User",
            "email": email,
            "role": "Engineer",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "API Integration User"
    assert data["email"] == email
    assert data["role"] == "Engineer"
    assert data["id"]

    session = SessionLocal()

    try:
        user = session.get(UserDB, data["id"])

        assert user is not None
        assert user.email == email

    finally:
        session.execute(
            delete(UserDB).where(UserDB.id == data["id"])
        )
        session.commit()
        session.close()
        
        
        
@pytest.mark.integration
def test_get_user_by_id():
    email = f"{uuid4()}@example.com"

    create_response = client.post(
        "/users",
        json={
            "name": "API Get User",
            "email": email,
            "role": "Engineer",
        },
    )

    assert create_response.status_code == 201

    user_id = create_response.json()["id"]

    try:
        response = client.get(f"/users/{user_id}")

        assert response.status_code == 200

        data = response.json()

        assert data["id"] == user_id
        assert data["name"] == "API Get User"
        assert data["email"] == email
        assert data["role"] == "Engineer"

    finally:
        session = SessionLocal()

        try:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
            session.commit()
        finally:
            session.close()
            
            
@pytest.mark.integration
def test_get_user_by_email():
    email = f"{uuid4()}@example.com"

    create_response = client.post(
        "/users",
        json={
            "name": "API Email User",
            "email": email,
            "role": "Engineer",
        },
    )

    assert create_response.status_code == 201

    user_id = create_response.json()["id"]

    try:
        response = client.get(f"/users/email/{email.upper()}")

        assert response.status_code == 200

        data = response.json()

        assert data["id"] == user_id
        assert data["name"] == "API Email User"
        assert data["email"] == email
        assert data["role"] == "Engineer"

    finally:
        session = SessionLocal()

        try:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
            session.commit()
        finally:
            session.close()
            
@pytest.mark.integration
def test_get_user_by_id_returns_404():
    response = client.get("/users/missing-user-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
    
    
@pytest.mark.integration
def test_get_user_by_email_returns_404():
    response = client.get("/users/email/missing@example.com")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"