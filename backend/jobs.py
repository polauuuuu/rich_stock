import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import uuid4

import httpx
import pandas as pd

from .store import now
from .providers import credentials, fetch_universe, fetch_bars, latest_completed_session
from .research import backtest, train_model


class Cancelled(Exception):
    pass


class Jobs:
    def __init__(self, store):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = Lock()
        self.events = {}

    def submit(self, config):
        if config['kind'] == 'download':
            credentials()
        with self.lock:
            if any(j['state'] in ('queued', 'running', 'cancelling') for j in self.store.jobs()):
                raise ValueError('已有工作執行中；請等候完成或取消。')
            job_id = uuid4().hex
            event = Event()
            self.events[job_id] = event
            with self.store.db() as db:
                db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',
                           (job_id, config['kind'], 'queued', 0, '等候執行', json.dumps(config), None, now()))
            self.pool.submit(self.run, job_id, config, event)
        return job_id

    def cancel(self, job_id):
        with self.lock:
            event = self.events.get(job_id)
            job = next((j for j in self.store.jobs() if j['id'] == job_id), None)
            if event is None or job is None or job['state'] not in ('queued', 'running', 'cancelling'):
                raise ValueError('工作不存在或已完成。')
            event.set()
            self.store.update(job_id, state='cancelling', message='正在取消；模型運算會於當前步驟完成後停止。')

    def run(self, job_id, config, event):
        def check():
            if event.is_set():
                raise Cancelled()
        def progress(p, message):
            check()
            self.store.update(job_id, progress=p, message=message)
        try:
            self.store.update(job_id, state='running')
            progress(.03, '準備數據')
            if config['kind'] == 'download':
                result = self.download(config, progress, check)
            else:
                frame = self.store.load(config['source'])
                progress(.12, '計算特徵及研究結果；大範圍實驗可能需時數分鐘。')
                result = (backtest(frame, config, check=check) if config['kind'] == 'backtest'
                          else train_model(frame, config, check))
            result['source'] = config['source']
            result['created'] = now()
            encoded = json.dumps(result, allow_nan=False)
            with self.lock:
                check()
                self.store.update(job_id, state='completed', progress=1, message='完成', result=encoded)
        except Cancelled:
            self.store.update(job_id, state='cancelled', message='已取消；已完成的股票檔案保留，可增量更新。')
        except Exception as error:
            # Known errors are curated; unexpected errors expose only the type, never headers/keys.
            message = str(error) if isinstance(error, ValueError) else f'工作失敗（{type(error).__name__}），請檢查日期、數據或服務日誌。'
            self.store.update(job_id, state='failed', message=message[:500])
        finally:
            with self.lock:
                self.events.pop(job_id, None)

    def download(self, config, progress, check):
        with httpx.Client(timeout=45) as public:
            universe, excluded = fetch_universe(public, check)
        snapshot = dict(updated=now(), included=universe, excluded=excluded)
        path = self.store.root / 'universe.json'
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
        selected = config.get('symbols', '').upper().replace(' ', '').split(',')
        symbols = selected if selected != [''] else [r['symbol'] for r in universe]
        end = min(config.get('end') or latest_completed_session(), latest_completed_session())
        start = config.get('start') or str((pd.Timestamp(end) - pd.DateOffset(years=1)).date())
        if start > end:
            raise ValueError('開始日期晚於最後完整交易日。')
        # Refresh entire per-symbol history when fetching: split-adjusted caches cannot safely append
        # only recent rows after a new corporate action without re-adjusting old units.
        coverage = self.store.coverage('live')
        if coverage['start']:
            start = min(start, coverage['start'])
            end = max(end, coverage['end'])
        completed, missing = [], []
        with httpx.Client(headers=credentials(), timeout=60) as client:
            for i in range(0, len(symbols), 50):
                check()
                batch = symbols[i:i + 50]
                progress(.05 + .9 * i / max(1, len(symbols)), f'SIP 下載 {i}/{len(symbols)} 隻；完整處理分頁')
                f = fetch_bars(client, batch, start, end, check)
                for symbol in batch:
                    part = f[f.symbol == symbol]
                    if part.empty:
                        missing.append(symbol)
                    else:
                        part = part.assign(fetched_at=now())
                        self.store.merge('live', symbol, part, replace=True)
                        completed.append(symbol)
        if not completed:
            raise ValueError('API 未返回任何股票數據；請檢查權限及符號。')
        return dict(downloaded=len(completed), requested=len(symbols), missing=missing, start=start, end=end,
                    adjustment='split', feed='sip', universe_updated=snapshot['updated'],
                    note='使用當前上市名單，有生存者偏差。為保持拆股調整一致，更新會重新抓取已保存期間；已完成檔案逐隻原子寫入。')
