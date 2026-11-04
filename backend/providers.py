import io
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from .research import sessions


def parse_directory(text):
    clean = '\n'.join(line for line in text.splitlines() if not line.startswith('File Creation'))
    data = pd.read_csv(io.StringIO(clean), sep='|', dtype=str).fillna('')
    kept, excluded = [], []
    for row in data.to_dict('records'):
        symbol = row.get('Symbol', row.get('ACT Symbol', ''))
        if not symbol or symbol.startswith('File Creation'):
            continue
        name = row.get('Security Name', '')
        reason = ('ETF' if row.get('ETF') == 'Y' else '測試證券' if row.get('Test Issue') == 'Y'
                  else '非普通股' if re.search(r'\b(warrants?|preferred|preference|units?|rights?|debentures?|notes?|bonds?)\b', name, re.I)
                  else '不支援符號' if not re.fullmatch(r'[A-Za-z0-9.\-]{1,16}', symbol) else '')
        record = dict(symbol=symbol, name=name)
        (excluded if reason else kept).append(record | ({'reason': reason} if reason else {}))
    return kept, excluded


def request(client, url, params=None, check=lambda: None):
    for attempt in range(5):
        check()
        try:
            response = client.get(url, params=params)
        except httpx.TransportError:
            if attempt == 4:
                raise ValueError('數據來源連線失敗，請檢查網絡後重試。') from None
        else:
            if response.status_code == 200:
                return response
            if response.status_code not in (429, 500, 502, 503, 504):
                raise ValueError(f'數據來源 HTTP {response.status_code}；請檢查 API 權限、日期或符號。')
        # Bounded, cancellable backoff; do not expose request headers or credentials.
        for _ in range(2 ** attempt * 4):
            check()
            time.sleep(.25)
    raise ValueError('數據來源繁忙或限速，重試次數已用盡。')


def fetch_universe(client, check):
    kept, excluded = [], []
    for filename in ['nasdaqlisted.txt']:
        text = request(client, 'https://www.nasdaqtrader.com/dynamic/SymDir/' + filename, check=check).text
        a, b = parse_directory(text)
        kept.extend(r | {'exchange':'NASDAQ'} for r in a)
        excluded.extend(b)
    return list({r['symbol']: r for r in kept}.values()), excluded


def latest_completed_session():
    now = datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo('America/New_York'))
    dates = sessions(str((local - timedelta(days=14)).date()), str(local.date()))
    import exchange_calendars as xcals
    calendar = xcals.get_calendar('XNYS')
    complete = [d for d in dates if calendar.session_close(d).to_pydatetime() + timedelta(minutes=15) < now]
    return complete[-1].strftime('%Y-%m-%d')


def fetch_bars(client, symbols, start, end, check):
    # End is inclusive at UI level. Request until next NY midnight, then retain completed session dates only.
    start_dt = pd.Timestamp(start).tz_localize('America/New_York')
    end_dt = (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize('America/New_York')
    end_utc = min(end_dt.tz_convert('UTC').to_pydatetime(), datetime.now(timezone.utc) - timedelta(minutes=16))
    params = dict(symbols=','.join(symbols), timeframe='1Day', start=start_dt.isoformat(),
                  end=end_utc.isoformat(), feed='sip', adjustment='split', limit=10000)
    rows, seen = [], set()
    while True:
        check()
        result = request(client, 'https://data.alpaca.markets/v2/stocks/bars', params, check).json()
        for symbol, bars in (result.get('bars') or {}).items():
            for b in bars:
                rows.append(dict(symbol=symbol, date=pd.Timestamp(b['t']).tz_convert('America/New_York').tz_localize(None).normalize(),
                                 open=b['o'], high=b['h'], low=b['l'], close=b['c'], volume=b['v']))
        token = result.get('next_page_token')
        if not token:
            break
        if token in seen:
            raise ValueError('API 重複分頁 token，已停止以避免無限查詢。')
        seen.add(token)
        params['page_token'] = token
        # Below Basic's 200 requests/minute, even with retries.
        time.sleep(.35)
    if not rows:
        return pd.DataFrame(columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'])
    f = pd.DataFrame(rows)
    valid = sessions(start, end)
    return f[f.date.isin(valid)].drop_duplicates(['symbol', 'date'])


def credentials():
    key, secret = os.getenv('ALPACA_API_KEY', ''), os.getenv('ALPACA_SECRET_KEY', '')
    if not key or not secret:
        raise ValueError('請先在 .env 設定 ALPACA_API_KEY 及 ALPACA_SECRET_KEY，再重新啟動服務。')
    return {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
