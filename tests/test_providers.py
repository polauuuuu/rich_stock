import httpx
import pandas as pd
import pytest
from backend.providers import fetch_bars, parse_directory


def test_universe_requests_nasdaq_only():
    from backend.providers import fetch_universe
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200,text='Symbol|Security Name|Test Issue|ETF\nTEST|Test Common Stock|N|N')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        included,_=fetch_universe(client,lambda:None)
    assert paths==['/dynamic/SymDir/nasdaqlisted.txt']
    assert included[0]['exchange']=='NASDAQ'


def test_pagination_reaches_later_symbols():
    calls = []
    def handler(request):
        calls.append(request.url.params.get('page_token'))
        symbol = 'A' if len(calls) == 1 else 'B'
        return httpx.Response(200, json={'bars': {symbol: [dict(t='2025-02-03T05:00:00Z', o=10, h=11, l=9, c=10, v=100)]},
                                         'next_page_token': 'page2' if len(calls) == 1 else None})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        f = fetch_bars(client, ['A', 'B'], '2025-02-03', '2025-02-04', lambda: None)
    assert set(f.symbol) == {'A', 'B'}
    assert calls == [None, 'page2']


def test_directory_filter_explains_exclusion():
    text = 'Symbol|Security Name|Test Issue|ETF\nA|A Common Stock|N|N\nB|B ETF|N|Y\nC|C Warrants|N|N\nFile Creation Time: x||||'
    kept, excluded = parse_directory(text)
    assert [r['symbol'] for r in kept] == ['A']
    assert len(excluded) == 2
