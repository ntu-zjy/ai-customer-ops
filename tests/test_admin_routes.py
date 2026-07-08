from fastapi.testclient import TestClient


def test_admin_users_page_renders_empty_state(app_env) -> None:
    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/admin/users")

    assert response.status_code == 200
    assert "暂无同步用户" in response.text


def test_healthz(app_env) -> None:
    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_v02_admin_pages_render(app_env) -> None:
    from app.main import create_app

    client = TestClient(create_app())
    for path in ["/admin/workbench", "/admin/dashboard", "/admin/rules", "/admin/settings/knowledge", "/admin/marketing"]:
        response = client.get(path)
        assert response.status_code == 200
