import pytest


SIGNUP_URL = "/auth/signup"
LOGIN_URL = "/auth/login"
ME_URL = "/auth/me"

VALID_USER = {"email": "test@example.com", "username": "testuser", "password": "password123"}


def auth_headers(client) -> dict:
    client.post(SIGNUP_URL, json=VALID_USER)
    res = client.post(LOGIN_URL, json={"email": VALID_USER["email"], "password": VALID_USER["password"]})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# --- signup ---

def test_signup_success(client):
    res = client.post(SIGNUP_URL, json={"email": "new@example.com", "username": "newuser", "password": "password123"})
    assert res.status_code == 201
    body = res.json()
    assert "access_token" in body
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["username"] == "newuser"


def test_signup_duplicate_email(client):
    payload = {"email": "dup@example.com", "username": "dupuser", "password": "password123"}
    client.post(SIGNUP_URL, json=payload)
    res = client.post(SIGNUP_URL, json=payload)
    assert res.status_code == 400
    assert "already registered" in res.json()["detail"].lower()


def test_signup_short_password(client):
    res = client.post(SIGNUP_URL, json={"email": "a@example.com", "username": "auser", "password": "short"})
    assert res.status_code == 422


def test_signup_short_username(client):
    res = client.post(SIGNUP_URL, json={"email": "b@example.com", "username": "ab", "password": "password123"})
    assert res.status_code == 422


def test_signup_invalid_username_chars(client):
    res = client.post(SIGNUP_URL, json={"email": "c@example.com", "username": "bad user!", "password": "password123"})
    assert res.status_code == 422


def test_signup_invalid_email(client):
    res = client.post(SIGNUP_URL, json={"email": "not-an-email", "username": "validuser", "password": "password123"})
    assert res.status_code == 422


# --- login ---

def test_login_success(client):
    client.post(SIGNUP_URL, json=VALID_USER)
    res = client.post(LOGIN_URL, json={"email": VALID_USER["email"], "password": VALID_USER["password"]})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client):
    client.post(SIGNUP_URL, json=VALID_USER)
    res = client.post(LOGIN_URL, json={"email": VALID_USER["email"], "password": "wrongpassword"})
    assert res.status_code == 401


def test_login_unknown_email(client):
    res = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "password123"})
    assert res.status_code == 401


# --- /auth/me ---

def test_me_authenticated(client):
    client.post(SIGNUP_URL, json=VALID_USER)
    login_res = client.post(LOGIN_URL, json={"email": VALID_USER["email"], "password": VALID_USER["password"]})
    token = login_res.json()["access_token"]
    res = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == VALID_USER["email"]


def test_me_no_token(client):
    res = client.get(ME_URL)
    assert res.status_code == 401


def test_me_invalid_token(client):
    res = client.get(ME_URL, headers={"Authorization": "Bearer invalidtoken"})
    assert res.status_code == 401
