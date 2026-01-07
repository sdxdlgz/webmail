import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app

EMPTY_DATA = {"users": [], "groups": [], "accounts": []}


@pytest.fixture()
def client(tmp_path: Path):
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(EMPTY_DATA), encoding="utf-8")

    settings = Settings(data_file_path=data_file)
    app = create_app(settings)

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def logged_in_client(client: TestClient):
    """Client with admin logged in"""
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return client


def test_batch_group_requires_auth(client: TestClient):
    """Test that batch-group endpoint requires authentication"""
    r = client.post("/api/accounts/batch-group", json={"ids": ["test-id"], "group_id": None})
    assert r.status_code == 401


def test_batch_group_empty_ids(logged_in_client: TestClient):
    """Test that batch-group rejects empty ids list"""
    r = logged_in_client.post("/api/accounts/batch-group", json={"ids": [], "group_id": None})
    assert r.status_code == 422


def test_batch_group_move_to_no_group(logged_in_client: TestClient, tmp_path: Path):
    """Test moving accounts to no group (removing from group)"""
    # First create a group
    r = logged_in_client.post("/api/groups", json={"name": "Test Group"})
    assert r.status_code == 201
    group_id = r.json()["id"]

    # Create an account in that group
    r = logged_in_client.post("/api/accounts", json={
        "email": "test@example.com",
        "refresh_token": "test_token",
        "client_id": "test_client_id",
        "group_id": group_id
    })
    assert r.status_code == 201
    account_id = r.json()["id"]

    # Verify account is in group
    r = logged_in_client.get("/api/accounts")
    assert r.status_code == 200
    account = next(a for a in r.json() if a["id"] == account_id)
    assert account["group_id"] == group_id

    # Move to no group
    r = logged_in_client.post("/api/accounts/batch-group", json={
        "ids": [account_id],
        "group_id": None
    })
    assert r.status_code == 200
    assert r.json()["updated"] == 1

    # Verify account is no longer in group
    r = logged_in_client.get("/api/accounts")
    account = next(a for a in r.json() if a["id"] == account_id)
    assert account["group_id"] is None


def test_batch_group_move_to_group(logged_in_client: TestClient):
    """Test moving accounts to a specific group"""
    # Create two groups
    r = logged_in_client.post("/api/groups", json={"name": "Group A"})
    assert r.status_code == 201
    group_a_id = r.json()["id"]

    r = logged_in_client.post("/api/groups", json={"name": "Group B"})
    assert r.status_code == 201
    group_b_id = r.json()["id"]

    # Create accounts in Group A
    account_ids = []
    for i in range(3):
        r = logged_in_client.post("/api/accounts", json={
            "email": f"test{i}@example.com",
            "refresh_token": f"test_token_{i}",
            "client_id": "test_client_id",
            "group_id": group_a_id
        })
        assert r.status_code == 201
        account_ids.append(r.json()["id"])

    # Move all accounts to Group B
    r = logged_in_client.post("/api/accounts/batch-group", json={
        "ids": account_ids,
        "group_id": group_b_id
    })
    assert r.status_code == 200
    assert r.json()["updated"] == 3

    # Verify all accounts are in Group B
    r = logged_in_client.get("/api/accounts")
    for account in r.json():
        if account["id"] in account_ids:
            assert account["group_id"] == group_b_id


def test_batch_group_invalid_group(logged_in_client: TestClient):
    """Test that batch-group rejects invalid group_id"""
    # Create an account
    r = logged_in_client.post("/api/accounts", json={
        "email": "test@example.com",
        "refresh_token": "test_token",
        "client_id": "test_client_id"
    })
    assert r.status_code == 201
    account_id = r.json()["id"]

    # Try to move to non-existent group
    r = logged_in_client.post("/api/accounts/batch-group", json={
        "ids": [account_id],
        "group_id": "non-existent-group-id"
    })
    assert r.status_code == 400
    assert "Group not found" in r.json()["detail"]


def test_batch_group_partial_update(logged_in_client: TestClient):
    """Test that batch-group only updates existing accounts"""
    # Create a group
    r = logged_in_client.post("/api/groups", json={"name": "Test Group"})
    assert r.status_code == 201
    group_id = r.json()["id"]

    # Create one account
    r = logged_in_client.post("/api/accounts", json={
        "email": "test@example.com",
        "refresh_token": "test_token",
        "client_id": "test_client_id"
    })
    assert r.status_code == 201
    account_id = r.json()["id"]

    # Try to update with mix of valid and invalid IDs
    r = logged_in_client.post("/api/accounts/batch-group", json={
        "ids": [account_id, "non-existent-id-1", "non-existent-id-2"],
        "group_id": group_id
    })
    assert r.status_code == 200
    # Only 1 account should be updated
    assert r.json()["updated"] == 1

    # Verify the existing account was updated
    r = logged_in_client.get("/api/accounts")
    account = next(a for a in r.json() if a["id"] == account_id)
    assert account["group_id"] == group_id
