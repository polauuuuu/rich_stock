import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        yield c


def test_demo_scan_and_secret_free_status(client):
    status = client.get('/api/status').json()
    assert status['datasets']['demo']['symbols'] == 32
    response = client.get('/api/scan', params={'source': 'demo', 'min_dollar_volume': 0})
    assert response.status_code == 200
    assert len(response.json()['rows']) >= 12
    assert 'secret' not in str(status).lower()


def test_live_never_falls_back_to_demo(client):
    r = client.get('/api/scan', params={'source': 'live'})
    assert r.status_code == 400


def test_input_validation(client):
    assert client.get('/api/scan', params={'down_days': 0}).status_code == 422
    assert client.post('/api/jobs', json={'kind': 'backtest', 'capital': -1}).status_code == 422


def test_no_keys_rejected(client, monkeypatch):
    monkeypatch.delenv('ALPACA_API_KEY', raising=False)
    monkeypatch.delenv('ALPACA_SECRET_KEY', raising=False)
    assert client.post('/api/jobs', json={'kind': 'download', 'source': 'live'}).status_code == 400


def test_partial_demo_is_rebuilt(tmp_path):
    from backend.store import Store
    import pandas as pd
    s = Store(tmp_path)
    s.merge('demo', 'PARTIAL', pd.DataFrame(dict(symbol=['PARTIAL'], date=pd.to_datetime(['2025-02-03']), open=[1], high=[2], low=[1], close=[1], volume=[100])))
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/status').json()['datasets']['demo']['symbols'] == 32
