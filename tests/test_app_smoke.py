import time
import re
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c

def test_register_login_profile_flow(client):
    # Unique email per run
    email = f"user{int(time.time())}@example.com"
    password = "pass1234"

    # Register
    resp = client.post('/register', data={
        'name': 'Test User',
        'phone': '9000000000',
        'email': email,
        'password': password,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Login' in resp.data or b'Login Avvandi' in resp.data

    # Login
    resp = client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)
    assert resp.status_code == 200

    # Access profile
    resp = client.get('/profile')
    assert resp.status_code == 200
    assert email.encode() in resp.data


def test_admin_protection_and_access(client):
    # As anonymous, admin pages redirect/forbid
    resp = client.get('/admin/buses', follow_redirects=False)
    assert resp.status_code in (301,302,303,307,308)

    # Simulate admin session
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_email'] = 'admin@example.com'
        sess['role'] = 'admin'

    # Now admin pages are allowed
    resp = client.get('/admin/buses')
    assert resp.status_code == 200
    resp = client.get('/admin/dashboard')
    assert resp.status_code == 200
