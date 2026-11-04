import pytest
import pandas as pd
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.store import Store

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        yield c

def test_no_synthetic_dataset_created(client, tmp_path):
    status=client.get('/api/status').json()
    assert list(status['datasets']) == ['live']
    assert status['datasets']['live']['symbols'] == 0
    assert not (tmp_path/'demo').exists()
    assert client.get('/api/scan',params={'source':'demo'}).status_code == 422

def test_live_scan_both_requires_red_candles(tmp_path):
    store=Store(tmp_path)
    f=pd.DataFrame(dict(symbol='TEST',date=pd.bdate_range('2025-02-03',periods=4),open=[10,9.5,8.5,6.5],high=[11,10,9,8],low=[9,8,7,6],close=[10,9,8,7],volume=[4000,3000,2000,1000]))
    store.merge('live','TEST',f)
    with TestClient(create_app(tmp_path)) as c:
        params={'min_dollar_volume':0,'min_price':0}
        assert c.get('/api/scan',params=params).json()['rows']==[]
        assert len(c.get('/api/scan',params=params|{'decline_mode':'close'}).json()['rows'])==1


def test_stock_chart_does_not_load_whole_market(tmp_path, monkeypatch):
    store=Store(tmp_path)
    f=pd.DataFrame(dict(symbol='TEST',date=pd.bdate_range('2025-02-03',periods=4),open=[11,10,9,8],high=[12,11,10,9],low=[9,8,7,6],close=[10,9,8,7],volume=[4000,3000,2000,1000]))
    store.merge('live','TEST',f)
    with TestClient(create_app(tmp_path)) as c:
        monkeypatch.setattr(Store,'load',lambda *args: (_ for _ in ()).throw(AssertionError('whole-market read')))
        assert len(c.get('/api/bars/TEST').json()['bars'])==4
        assert c.get('/api/status').json()['datasets']['live']['bars']==4

def test_empty_live_has_clear_error(client):
    assert client.get('/api/scan').status_code == 400

def test_input_validation(client):
    assert client.get('/api/scan',params={'down_days':0}).status_code == 422
    assert client.post('/api/jobs',json={'kind':'backtest','capital':-1}).status_code == 422

def test_no_keys_rejected(client, monkeypatch):
    monkeypatch.delenv('ALPACA_API_KEY',raising=False)
    monkeypatch.delenv('ALPACA_SECRET_KEY',raising=False)
    assert client.post('/api/jobs',json={'kind':'download','source':'live'}).status_code == 400
