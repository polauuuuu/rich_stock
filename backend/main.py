import io
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from .store import Store
from .demo import generate_demo
from .jobs import Jobs
from .research import DEFAULTS, features, candidate_mask


class Experiment(BaseModel):
    kind: Literal['backtest', 'train', 'download']
    source: Literal['demo', 'live'] = 'demo'
    start: date | None = None
    end: date | None = None
    down_days: int = Field(3, ge=1, le=10)
    volume_days: int = Field(3, ge=1, le=10)
    min_price: float = Field(5, ge=0, le=100000)
    min_dollar_volume: float = Field(1_000_000, ge=0)
    holding_days: int = Field(5, ge=1, le=60)
    stop_loss: float = Field(.05, gt=0, lt=1)
    take_profit: float = Field(.10, gt=0, le=10)
    cost_bps: float = Field(10, ge=0, le=500)
    max_positions: int = Field(5, ge=1, le=50)
    capital: float = Field(100000, ge=100, le=1e10)
    top_k: int = Field(5, ge=1, le=50)
    model: Literal['logistic', 'tree'] = 'logistic'
    symbols: str = Field('', max_length=5000, pattern=r'^[A-Za-z0-9.,\-\s]*$')

    @model_validator(mode='after')
    def dates_valid(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError('開始日期必須早於結束日期')
        if self.kind == 'download' and self.source != 'live':
            raise ValueError('下載只支援 live 模式')
        return self


def records(f):
    return json.loads(f.to_json(orient='records', date_format='iso'))


def create_app(root=None):
    @asynccontextmanager
    async def lifespan(app):
        store = Store(root or os.getenv('DATA_DIR', 'data'))
        marker = store.root / 'demo.complete.json'
        if not marker.exists():
            demo = generate_demo()
            for symbol, part in demo.groupby('symbol'):
                store.merge('demo', symbol, part, replace=True)
            temp = marker.with_suffix('.tmp')
            temp.write_text(json.dumps({'version': 1, 'symbols': sorted(demo.symbol.unique())}), encoding='utf-8')
            temp.replace(marker)
        app.state.store = store
        app.state.jobs = Jobs(store)
        yield
        for event in list(app.state.jobs.events.values()):
            event.set()
        app.state.jobs.pool.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title='Rich Stock Research API', lifespan=lifespan)

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={'detail': str(error)})

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/status')
    def status():
        path = app.state.store.root / 'universe.json'
        universe = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        return dict(datasets={s: app.state.store.coverage(s) for s in ['demo', 'live']},
                    credentials_configured=bool(os.getenv('ALPACA_API_KEY') and os.getenv('ALPACA_SECRET_KEY')),
                    universe=dict(updated=universe['updated'], included=len(universe['included']), excluded=len(universe['excluded'])) if universe else None,
                    warning='今日股票池有生存者偏差；合成示範數據只用作測試介面，唔係歷史投資成績。')

    def scan_frame(source, as_of, down_days, volume_days, min_price, min_dollar_volume):
        f = app.state.store.load(source)
        if as_of:
            f = f[f.date <= pd.Timestamp(as_of)]
        if f.empty:
            raise ValueError('所選日期之前冇數據。')
        latest = f.date.max()
        f = features(f, down_days, volume_days)
        rows = f[(f.date == latest) & candidate_mask(f, dict(min_price=min_price, min_dollar_volume=min_dollar_volume))]
        return rows.sort_values('volume_ratio'), str(latest.date()), f.symbol.nunique()

    @app.get('/api/scan')
    def scan(source: Literal['demo', 'live'] = 'demo', as_of: date | None = None,
             down_days: int = Query(3, ge=1, le=10), volume_days: int = Query(3, ge=1, le=10),
             min_price: float = Query(5, ge=0), min_dollar_volume: float = Query(1000000, ge=0)):
        f, effective, total = scan_frame(source, as_of, down_days, volume_days, min_price, min_dollar_volume)
        return dict(rows=records(f), as_of=effective, universe=total, source=source)

    @app.get('/api/export')
    def export(source: Literal['demo', 'live'] = 'demo', as_of: date | None = None,
               down_days: int = Query(3, ge=1, le=10), volume_days: int = Query(3, ge=1, le=10),
               min_price: float = Query(5, ge=0), min_dollar_volume: float = Query(1000000, ge=0)):
        f, _, _ = scan_frame(source, as_of, down_days, volume_days, min_price, min_dollar_volume)
        return Response(f.to_csv(index=False).encode('utf-8-sig'), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="rich-stock-scan.csv"'})

    @app.get('/api/bars/{symbol}')
    def bars(symbol: str, source: Literal['demo', 'live'] = 'demo', as_of: date | None = None,
             down_days: int = Query(3, ge=1, le=10), volume_days: int = Query(3, ge=1, le=10)):
        f = app.state.store.load(source)
        f = f[f.symbol == symbol.upper()]
        if as_of:
            f = f[f.date <= pd.Timestamp(as_of)]
        if f.empty:
            raise HTTPException(404, '搵唔到呢隻股票嘅數據。')
        out = features(f, down_days, volume_days).tail(300)
        return dict(symbol=symbol.upper(), source=source, bars=records(out))

    @app.get('/api/jobs')
    def jobs():
        return app.state.store.jobs()

    @app.post('/api/jobs', status_code=202)
    def submit(config: Experiment):
        return dict(id=app.state.jobs.submit(config.model_dump(mode='json', exclude_none=True)))

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel(job_id: str):
        app.state.jobs.cancel(job_id)
        return {'status': 'cancelling'}

    @app.get('/api/results/{job_id}')
    def result(job_id: str):
        try:
            return app.state.store.result(job_id)
        except KeyError:
            raise HTTPException(404, '工作不存在。')

    return app


app = create_app()
