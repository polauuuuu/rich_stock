import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone

import pandas as pd


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.cache = {}
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

    def load(self, source):
        with self.lock:
            if source not in self.cache:
                paths = sorted((self.root / source).glob('*.parquet'))
                if not paths:
                    raise ValueError('未有真實歷史數據，請先到數據管理下載。')
                self.cache[source] = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
                marker = self.root / 'demo.complete.json'
                if source == 'demo' and marker.exists():
                    allowed = json.loads(marker.read_text())['symbols']
                    self.cache[source] = self.cache[source][self.cache[source].symbol.isin(allowed)]
            return self.cache[source].copy()

    def coverage(self, source):
        try:
            f = self.load(source)
            return dict(symbols=f.symbol.nunique(), bars=len(f), start=str(f.date.min().date()),
                        end=str(f.date.max().date()), adjustment='split', feed='synthetic' if source == 'demo' else 'sip')
        except ValueError:
            return dict(symbols=0, bars=0, start=None, end=None)

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
