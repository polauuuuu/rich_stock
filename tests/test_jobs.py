import json
import time
from threading import Event
import pandas as pd
import pytest
from backend.store import Store
from backend.jobs import Jobs


def test_job_completes_and_persists_result(tmp_path):
    store = Store(tmp_path)
    dates = pd.bdate_range('2025-02-03', periods=7)
    prices = [10, 9, 8, 7, 6, 6, 6]
    f = pd.DataFrame(dict(symbol='A', date=dates, open=prices, high=[p*1.01 for p in prices],
                          low=[p*.99 for p in prices], close=prices, volume=[4000,3000,2000,1000,2000,2000,2000]))
    store.merge('demo', 'A', f)
    jobs = Jobs(store)
    job_id = jobs.submit(dict(kind='backtest', source='demo', min_dollar_volume=0, holding_days=2))
    jobs.pool.shutdown(wait=True)
    assert store.jobs()[0]['state'] == 'completed'
    assert store.result(job_id)['metrics']['trades'] == 1
    assert Store(tmp_path).result(job_id)['source'] == 'demo'


def test_restart_marks_unfinished_work_interrupted(tmp_path):
    s = Store(tmp_path)
    with s.db() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)', ('x','train','running',.2,'work','{}',None,'2025-01-01'))
    assert Store(tmp_path).jobs()[0]['state'] == 'interrupted'


def test_cancellation_is_not_success(tmp_path):
    s = Store(tmp_path)
    j = Jobs(s)
    with s.db() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)', ('x','backtest','queued',0,'work','{}',None,'2025-01-01'))
    event = Event()
    event.set()
    j.run('x', dict(kind='backtest', source='demo'), event)
    j.pool.shutdown()
    assert s.jobs()[0]['state'] == 'cancelled'


def test_cancel_does_not_overwrite_completed_state(tmp_path):
    s = Store(tmp_path)
    j = Jobs(s)
    with s.db() as db:
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)', ('x','train','completed',1,'done','{}','{}','2025-01-01'))
    j.events['x'] = Event()  # Completion committed; worker has not cleaned up event yet.
    with pytest.raises(ValueError):
        j.cancel('x')
    assert s.jobs()[0]['state'] == 'completed'
    j.pool.shutdown()


def test_replace_rejects_incomplete_adjusted_history(tmp_path):
    (tmp_path/'universe.json').write_text(json.dumps({'scope':'nasdaq','included':[{'symbol':'A'}]}))
    s = Store(tmp_path)
    old = pd.DataFrame(dict(symbol=['A','A'], date=pd.to_datetime(['2025-02-03','2025-02-04']), close=[10,12]))
    s.merge('live', 'A', old)
    with pytest.raises(ValueError, match='不完整'):
        s.merge('live', 'A', old.iloc[:1].assign(close=5), replace=True)
    assert s.load('live').close.tolist() == [10, 12]
    s.merge('live', 'A', old.assign(close=[5,6]), replace=True)
    assert s.load('live').close.tolist() == [5, 6]
