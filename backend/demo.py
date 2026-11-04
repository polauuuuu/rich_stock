import numpy as np
import pandas as pd
from .research import sessions


def generate_demo():
    """Synthetic prices for interface testing, never actual histories of these tickers."""
    names = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'TSLA', 'AMD', 'AVGO', 'NFLX',
             'CRM', 'ADBE', 'INTC', 'QCOM', 'MU', 'PLTR', 'COIN', 'UBER', 'SHOP', 'SQ',
             'JPM', 'BAC', 'V', 'MA', 'XOM', 'CVX', 'WMT', 'COST', 'DIS', 'NKE', 'BA', 'CAT']
    rng = np.random.default_rng(42)
    dates = sessions('2019-01-02', '2026-11-03')
    market = rng.normal(.0002, .009, len(dates))
    rows = []
    for i, symbol in enumerate(names):
        daily = market + rng.normal(.0001, .018 + i % 4 * .003, len(dates))
        close = (30 + i * 7) * np.exp(np.cumsum(daily))
        op = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, .004, len(dates)))
        vol = rng.lognormal(15.2, .5, len(dates)).astype(int)
        if i < 12:
            close[-3:] = close[-4] * np.array([.985, .97, .962])
            op[-3:] = np.r_[close[-4], close[-3:-1]]
            vol[-3:] = [2_000_000, 1_500_000, 900_000]
        high = np.maximum(op, close) * (1 + rng.uniform(.001, .02, len(dates)))
        low = np.minimum(op, close) * (1 - rng.uniform(.001, .02, len(dates)))
        rows.append(pd.DataFrame(dict(symbol=symbol, date=dates, open=op, high=high,
                                      low=low, close=close, volume=vol)))
    return pd.concat(rows, ignore_index=True)
