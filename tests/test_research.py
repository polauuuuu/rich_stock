import pandas as pd
import pytest

from backend.research import features, backtest, chronological_split


def test_sessions_accept_holiday_boundaries():
    from backend.research import sessions
    assert str(sessions('2026-01-01','2026-01-04')[0].date()) == '2026-01-02'


def frame(prices, volumes=None, dates=None):
    dates = dates if dates is not None else pd.bdate_range('2025-02-03', periods=len(prices))
    return pd.DataFrame({'symbol': 'TEST', 'date': dates, 'open': prices,
                         'high': [p * 1.01 for p in prices], 'low': [p * .99 for p in prices],
                         'close': prices, 'volume': volumes or [1000] * len(prices)})


def test_three_declines_need_four_closes():
    f = features(frame([10, 9, 8, 7], [4000, 3000, 2000, 1000]), 3, 3)
    assert f.signal.tolist() == [False, False, False, True]


def test_declining_closes_can_include_green_candle():
    f = frame([10,9,8,7],[4000,3000,2000,1000])
    f['open'] = [10,9.5,8.5,6.5]  # Last candle green despite close-to-close decline.
    assert features(f,3,3,decline_mode='close').signal.iloc[-1]
    assert not features(f,3,3,decline_mode='both').signal.iloc[-1]
    f.loc[3,'open']=7.5
    assert features(f,3,3,decline_mode='both').signal.iloc[-1]


def test_candle_mode_needs_three_candles_not_four_closes():
    f=frame([10,11,12],[3000,2000,1000])
    f['open']=[11,12,13]
    f['high']=[12,13,14]
    assert features(f,3,3,decline_mode='candle').signal.iloc[-1]
    assert not features(f,3,3,decline_mode='both').signal.iloc[-1]


def test_missing_session_breaks_signal():
    f = features(frame([10, 9, 8, 7], [4000, 3000, 2000, 1000],
                       pd.to_datetime(['2025-02-03', '2025-02-04', '2025-02-06', '2025-02-07'])), 3, 3)
    assert not f.signal.any()


def test_next_open_and_costs():
    f = frame([10, 9, 8, 7, 6, 6, 6], [4000, 3000, 2000, 1000, 2000, 2000, 2000])
    r = backtest(f, {'holding_days': 2, 'stop_loss': .5, 'take_profit': .5,
                     'cost_bps': 10, 'min_dollar_volume': 0, 'min_price': 0})
    assert r['trades'][0]['entry_price'] == 6
    assert r['trades'][0]['entry_date'] == '2025-02-07'
    assert r['trades'][0]['return_pct'] == pytest.approx((.999 / 1.001 - 1) * 100)
    assert r['metrics']['total_return_pct'] < 0


def test_gap_stop_and_dual_touch():
    f = frame([10, 9, 8, 7, 10, 8, 8], [4000, 3000, 2000, 1000, 2000, 2000, 2000])
    r = backtest(f, {'holding_days': 3, 'stop_loss': .05, 'take_profit': .1,
                     'cost_bps': 0, 'min_dollar_volume': 0})
    assert r['trades'][0]['exit_price'] == 8
    f.loc[4, ['high', 'low']] = [12, 8]
    r = backtest(f, {'holding_days': 3, 'stop_loss': .05, 'take_profit': .1,
                     'cost_bps': 0, 'min_dollar_volume': 0})
    assert r['trades'][0]['exit_price'] == 9.5


def test_capital_and_position_limit():
    f = frame([10, 9, 8, 7, 6, 6, 6], [4000, 3000, 2000, 1000, 2000, 2000, 2000])
    f = pd.concat([f.assign(symbol=s) for s in ['A', 'B', 'C']])
    r = backtest(f, {'holding_days': 2, 'max_positions': 1, 'capital': 100,
                     'min_dollar_volume': 0, 'cost_bps': 10})
    assert len(r['trades']) == 1
    assert all(p['cash'] >= -1e-8 for p in r['equity'])


def test_split_purges_label_overlap():
    f = pd.DataFrame({'date': pd.bdate_range('2024-01-01', periods=100)})
    f['label_end'] = f.date.shift(-10)
    train, val, test = chronological_split(f)
    assert train.label_end.max() < val.date.min()
    assert val.label_end.max() < test.date.min()
