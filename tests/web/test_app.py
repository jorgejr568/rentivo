class TestApp:
    def test_home_redirects_to_billings(self, auth_client):
        response = auth_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/billings/" in response.headers["location"]

    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]
