import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone

import pandas as pd
import pyarrow.parquet as pq


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.cache = {}
        self.summaries = {}
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT, state TEXT, progress REAL, message TEXT, config TEXT, result TEXT, created TEXT)')
            db.execute("UPDATE jobs SET state='interrupted', message='服務重啟，工作已中斷；可重新提交。' WHERE state IN ('queued','running','cancelling')")

    def db(self):
        db = sqlite3.connect(self.root / 'research.sqlite', timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def merge(self, source, symbol, frame, replace=False):
        directory = self.root / source
        directory.mkdir(exist_ok=True)
        path = directory / (hashlib.sha256(symbol.encode()).hexdigest() + '.parquet')
        with self.lock:
            old = pd.read_parquet(path) if path.exists() else pd.DataFrame()
            if replace and not old.empty and not set(old.date).issubset(set(frame.date)):
                raise ValueError(f'{symbol} 更新回應不完整，已保留舊檔；請擴展日期或檢查 API 缺失資料後重試。')
            f = (frame.copy() if replace else pd.concat([old, frame], ignore_index=True))
            f = f.drop_duplicates(['symbol', 'date'], keep='last').sort_values('date')
            temp = path.with_suffix('.tmp')
            f.to_parquet(temp, index=False)
            temp.replace(path)
            self.cache.pop(source, None)
            if source in self.summaries:
                self.summaries[source][path.name] = dict(bars=len(f), start=f.date.min(), end=f.date.max())

    def load_symbol(self, source, symbol):
        path = self.root / source / (hashlib.sha256(symbol.encode()).hexdigest() + '.parquet')
        with self.lock:
            if not path.exists():
                return pd.DataFrame(columns=['symbol','date','open','high','low','close','volume'])
            return pd.read_parquet(path)

    def load(self, source):
        with self.lock:
            if source not in self.cache:
                paths = sorted((self.root / source).glob('*.parquet'))
                if not paths:
                    raise ValueError('未有真實歷史數據，請先到數據管理下載。')
                self.cache[source] = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
            return self.cache[source].copy()

    def coverage(self, source):
        with self.lock:
            if source not in self.summaries:
                summaries = {}
                for path in (self.root / source).glob('*.parquet'):
                    meta = pq.read_metadata(path)
                    if not meta.num_rows:
                        continue
                    index = meta.schema.names.index('date')
                    stats = [meta.row_group(i).column(index).statistics for i in range(meta.num_row_groups)]
                    summaries[path.name] = dict(bars=meta.num_rows, start=min(s.min for s in stats), end=max(s.max for s in stats))
                self.summaries[source] = summaries
            values = list(self.summaries[source].values())
            return dict(symbols=len(values), bars=sum(s['bars'] for s in values),
                        start=str(pd.Timestamp(min(s['start'] for s in values)).date()) if values else None,
                        end=str(pd.Timestamp(max(s['end'] for s in values)).date()) if values else None,
                        adjustment='split', feed='sip')

    def jobs(self):
        with self.db() as db:
            rows = db.execute('SELECT id, kind, state, progress, message, config, created FROM jobs ORDER BY created DESC LIMIT 40').fetchall()
        return [dict(r) | {'config': json.loads(r['config'])} for r in rows]

    def update(self, job_id, **fields):
        with self.db() as db:
            db.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', [*fields.values(), job_id])

    def result(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT result FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return json.loads(row['result']) if row['result'] else None
