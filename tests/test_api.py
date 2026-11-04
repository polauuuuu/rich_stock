import pytest
import pandas as pd
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.store import Store
import json

def install_nasdaq(tmp_path, symbols):
    (tmp_path/'universe.json').write_text(json.dumps({'scope':'nasdaq','updated':'2026-11-04','included':[{'symbol':s} for s in symbols],'excluded':[]}))

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
    install_nasdaq(tmp_path,['TEST'])
    store=Store(tmp_path)
    f=pd.DataFrame(dict(symbol='TEST',date=pd.bdate_range('2025-02-03',periods=4),open=[10,9.5,8.5,6.5],high=[11,10,9,8],low=[9,8,7,6],close=[10,9,8,7],volume=[4000,3000,2000,1000]))
    store.merge('live','TEST',f)
    with TestClient(create_app(tmp_path)) as c:
        params={'min_dollar_volume':0,'min_price':0}
        assert c.get('/api/scan',params=params).json()['rows']==[]
        assert len(c.get('/api/scan',params=params|{'decline_mode':'close'}).json()['rows'])==1


def test_stock_chart_does_not_load_whole_market(tmp_path, monkeypatch):
    install_nasdaq(tmp_path,['TEST'])
    store=Store(tmp_path)
    f=pd.DataFrame(dict(symbol='TEST',date=pd.bdate_range('2025-02-03',periods=4),open=[11,10,9,8],high=[12,11,10,9],low=[9,8,7,6],close=[10,9,8,7],volume=[4000,3000,2000,1000]))
    store.merge('live','TEST',f)
    with TestClient(create_app(tmp_path)) as c:
        monkeypatch.setattr(Store,'load',lambda *args: (_ for _ in ()).throw(AssertionError('whole-market read')))
        assert len(c.get('/api/bars/TEST').json()['bars'])==4
        assert c.get('/api/status').json()['datasets']['live']['bars']==4


def test_nasdaq_scope_excludes_previously_downloaded_other_exchanges(tmp_path):
    import json
    store=Store(tmp_path)
    f=pd.DataFrame(dict(symbol='NAS',date=pd.bdate_range('2025-02-03',periods=4),open=[11,10,9,8],high=[12,11,10,9],low=[9,8,7,6],close=[10,9,8,7],volume=[4000,3000,2000,1000]))
    store.merge('live','NAS',f)
    store.merge('live','OTHER',f.assign(symbol='OTHER'))
    (tmp_path/'universe.json').write_text(json.dumps({'scope':'nasdaq','updated':'2026-11-04','included':[{'symbol':'NAS'}],'excluded':[]}))
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/status').json()['datasets']['live']['symbols']==1
        rows=c.get('/api/scan',params={'min_dollar_volume':0,'min_price':0}).json()['rows']
        assert [r['symbol'] for r in rows]==['NAS']
        assert c.get('/api/bars/OTHER').status_code==400
    assert store.load('live').symbol.unique().tolist()==['NAS']


def test_missing_nasdaq_snapshot_cannot_expose_legacy_bars(tmp_path):
    store=Store(tmp_path)
    store.merge('live','OTHER',pd.DataFrame({'symbol':['OTHER'],'date':pd.to_datetime(['2025-02-03']),'open':[1],'high':[2],'low':[1],'close':[1],'volume':[100]}))
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/scan').status_code==400
        assert c.get('/api/bars/OTHER').status_code==400
        assert c.get('/api/status').status_code==400

def test_empty_live_has_clear_error(client):
    assert client.get('/api/scan').status_code == 400

def test_input_validation(client):
    assert client.get('/api/scan',params={'down_days':0}).status_code == 422
    assert client.post('/api/jobs',json={'kind':'backtest','capital':-1}).status_code == 422

def test_no_keys_rejected(client, monkeypatch):
    monkeypatch.delenv('ALPACA_API_KEY',raising=False)
    monkeypatch.delenv('ALPACA_SECRET_KEY',raising=False)
    assert client.post('/api/jobs',json={'kind':'download','source':'live'}).status_code == 400
