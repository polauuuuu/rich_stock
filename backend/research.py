"""Causal daily-bar research. All prices share the dataset's split-adjusted units."""
from functools import lru_cache

import numpy as np
import pandas as pd
import exchange_calendars as xcals

FEATURES = ['return_3', 'return_20', 'volume_ratio', 'ma_distance', 'volatility', 'dollar_volume']
DEFAULTS = dict(down_days=3, volume_days=3, min_price=5, min_dollar_volume=1_000_000,
                holding_days=5, stop_loss=.05, take_profit=.10, cost_bps=10,
                max_positions=5, capital=100_000, top_k=5)


@lru_cache(maxsize=32)
def sessions(start, end):
    cal = xcals.get_calendar('XNYS', start=start, end=end)
    return cal.sessions_in_range(start, end).tz_localize(None)


def features(frame, down_days=3, volume_days=3):
    f = frame.copy().sort_values(['symbol', 'date']).reset_index(drop=True)
    f['date'] = pd.to_datetime(f.date).dt.tz_localize(None).dt.normalize()
    if f.empty:
        return f.assign(signal=False)
    valid = sessions(str(f.date.min().date()), str(f.date.max().date()))
    session_ids = pd.Series(np.arange(len(valid)), index=valid)
    f['_session'] = f.date.map(session_ids)
    g = f.groupby('symbol', sort=False)
    decline = g.close.diff().lt(0)
    shrink = g.volume.diff().lt(0)
    f['signal'] = decline.groupby(f.symbol).transform(lambda s: s.rolling(down_days).sum().eq(down_days))
    if volume_days > 1:
        f['signal'] &= shrink.groupby(f.symbol).transform(lambda s: s.rolling(volume_days - 1).sum().eq(volume_days - 1))
    n = max(down_days, volume_days - 1)
    contiguous = g['_session'].diff().eq(1)
    f['signal'] &= contiguous.groupby(f.symbol).transform(lambda s: s.rolling(n).sum().eq(n))
    valid_bar = f[['open', 'high', 'low', 'close', 'volume']].gt(0).all(axis=1)
    f['signal'] &= valid_bar.groupby(f.symbol).transform(lambda s: s.rolling(n + 1).sum().eq(n + 1))
    f['return_3'] = g.close.pct_change(3, fill_method=None)
    f['return_20'] = g.close.pct_change(20, fill_method=None)
    mean_v = g.volume.transform(lambda s: s.rolling(20, min_periods=5).mean())
    f['volume_ratio'] = f.volume / mean_v
    f['ma_distance'] = f.close / g.close.transform(lambda s: s.rolling(20, min_periods=5).mean()) - 1
    daily = g.close.pct_change(fill_method=None)
    f['volatility'] = daily.groupby(f.symbol).transform(lambda s: s.rolling(20, min_periods=5).std())
    f['dollar_volume'] = (f.close * f.volume).groupby(f.symbol).transform(lambda s: s.rolling(20, min_periods=1).mean())
    return f.drop(columns='_session').replace([np.inf, -np.inf], np.nan)


def candidate_mask(f, cfg):
    return f.signal & f.close.ge(cfg['min_price']) & f.dollar_volume.ge(cfg['min_dollar_volume'])


def backtest(frame, config, scores=None, check=lambda: None):
    cfg = DEFAULTS | config
    f = features(frame, cfg['down_days'], cfg['volume_days'])
    if cfg.get('start'):
        f = f[f.date >= pd.Timestamp(cfg['start'])]
    if cfg.get('end'):
        f = f[f.date <= pd.Timestamp(cfg['end'])]
    if f.empty:
        raise ValueError('所選日期冇可用數據。')
    dates = sessions(str(f.date.min().date()), str(f.date.max().date()))
    by_date = {d: s.set_index('symbol') for d, s in f.groupby('date')}
    cash = float(cfg['capital'])
    cost = cfg['cost_bps'] / 10000
    positions, trades, curve, pending = {}, [], [], []
    for date in dates:
        check()
        day = by_date.get(date, pd.DataFrame())
        # Allocate using prior-close portfolio value. Never spend proceeds from today's close.
        allocation = (cash + sum(p['qty'] * p['mark'] for p in positions.values())) / cfg['max_positions']
        for symbol in pending:
            if symbol in positions or len(positions) >= cfg['max_positions'] or symbol not in day.index:
                continue
            price = float(day.loc[symbol, 'open'])
            if not np.isfinite(price) or price <= 0:
                continue
            qty = int(min(cash, allocation) / (price * (1 + cost)))
            if qty <= 0:
                continue
            basis = qty * price * (1 + cost)
            cash -= basis
            positions[symbol] = dict(symbol=symbol, entry_date=date.strftime('%Y-%m-%d'),
                                     entry_price=price, qty=qty, basis=basis, age=0, mark=price)
        for symbol, p in list(positions.items()):
            p['age'] += 1
            if symbol not in day.index:
                continue  # Retain and mark stale; never pretend a missing quote was an executable exit.
            row = day.loc[symbol]
            p['mark'] = float(row.close)
            stop, target = p['entry_price'] * (1 - cfg['stop_loss']), p['entry_price'] * (1 + cfg['take_profit'])
            exit_price, reason = None, None
            if row.open <= stop:
                exit_price, reason = float(row.open), '跳空止蝕'
            elif row.open >= target:
                exit_price, reason = float(row.open), '跳空止賺'
            elif row.low <= stop:
                exit_price, reason = stop, '止蝕（同日雙觸發亦先止蝕）'
            elif row.high >= target:
                exit_price, reason = target, '止賺'
            elif p['age'] >= cfg['holding_days']:
                exit_price, reason = float(row.close), '持有期結束'
            if exit_price is not None:
                proceeds = p['qty'] * exit_price * (1 - cost)
                cash += proceeds
                trades.append({**p, 'exit_date': date.strftime('%Y-%m-%d'), 'exit_price': exit_price,
                               'reason': reason, 'pnl': proceeds - p['basis'],
                               'return_pct': (proceeds / p['basis'] - 1) * 100})
                del positions[symbol]
        equity = cash + sum(p['qty'] * p['mark'] for p in positions.values())
        curve.append(dict(date=date.strftime('%Y-%m-%d'), equity=equity, cash=cash))
        pending = []
        if not day.empty:
            eligible = day[candidate_mask(day, cfg)].copy()
            eligible['rank'] = eligible.volume_ratio
            if scores is not None:
                eligible['rank'] = [-scores.get((s, date.strftime('%Y-%m-%d')), -np.inf) for s in eligible.index]
                eligible = eligible[np.isfinite(eligible['rank'])]
            pending = eligible.sort_values(['rank'], kind='stable').index.tolist()[:cfg['top_k']]
    eq = pd.Series([x['equity'] for x in curve])
    returns = [t['return_pct'] for t in trades]
    return dict(equity=curve, trades=trades, open_positions=list(positions.values()), config=cfg,
                metrics=dict(total_return_pct=(eq.iloc[-1] / cfg['capital'] - 1) * 100,
                             max_drawdown_pct=float((eq / eq.cummax() - 1).min() * 100),
                             win_rate_pct=float(np.mean(np.array(returns) > 0) * 100) if returns else 0,
                             average_trade_pct=float(np.mean(returns)) if returns else 0,
                             trades=len(trades), open_positions=len(positions)))


def chronological_split(data):
    dates = sorted(data.date.unique())
    if len(dates) < 30:
        raise ValueError('有效日期太少：至少需要 30 個候選訊號日期。')
    a, b = pd.Timestamp(dates[int(len(dates) * .6)]), pd.Timestamp(dates[int(len(dates) * .8)])
    return (data[(data.date < a) & (data.label_end < a)],
            data[(data.date >= a) & (data.date < b) & (data.label_end < b)],
            data[data.date >= b])


def train_model(frame, config, check=lambda: None):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score

    cfg = DEFAULTS | config
    f = features(frame, cfg['down_days'], cfg['volume_days'])
    if cfg.get('start'):
        f = f[f.date >= pd.Timestamp(cfg['start'])].copy()
    if cfg.get('end'):
        f = f[f.date <= pd.Timestamp(cfg['end'])].copy()
    g = f.groupby('symbol')
    h = cfg['holding_days']
    f['entry'] = g.open.shift(-1)
    f['exit'] = g.close.shift(-h)
    f['label_end'] = g.date.shift(-h)
    # Reject label windows with missing sessions instead of treating h rows as h sessions.
    if f.empty:
        raise ValueError('所選日期冇可用數據。')
    idx = pd.Series(range(len(sessions(str(f.date.min().date()), str(f.date.max().date())))),
                    index=sessions(str(f.date.min().date()), str(f.date.max().date())))
    contiguous = f.label_end.map(idx) - f.date.map(idx) == h
    cost = cfg['cost_bps'] / 10000
    f['forward_return'] = f['exit'] * (1 - cost) / (f.entry * (1 + cost)) - 1
    data = f[candidate_mask(f, cfg) & contiguous].dropna(subset=FEATURES + ['forward_return', 'label_end']).copy()
    data['target'] = data.forward_return.gt(0).astype(int)
    train, val, test = chronological_split(data)
    for name, split in [('訓練', train), ('驗證', val), ('測試', test)]:
        if len(split) < 30 or split.target.nunique() < 2:
            raise ValueError(f'{name}樣本不足：需要至少 30 筆及正負兩類；目前 {len(split)} 筆。請下載更多年份或放寬篩選。')
    check()
    model = (make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42))
             if cfg.get('model', 'logistic') == 'logistic'
             else HistGradientBoostingClassifier(max_iter=80, max_leaf_nodes=15, l2_regularization=2, random_state=42))
    model.fit(train[FEATURES], train.target)
    check()
    def evaluate(split):
        out = split.copy()
        out['score'] = model.predict_proba(out[FEATURES])[:, 1]
        top = out.sort_values('score', ascending=False).groupby('date').head(cfg['top_k'])
        return dict(samples=len(out), start=str(out.date.min().date()), end=str(out.date.max().date()),
                    positive_rate=float(out.target.mean()), pr_auc=float(average_precision_score(out.target, out.score)),
                    roc_auc=float(roc_auc_score(out.target, out.score)), top_k_hit_rate=float(top.target.mean())), out
    vm, _ = evaluate(val)
    tm, predictions = evaluate(test)
    scores = {(r.symbol, str(r.date.date())): r.score for r in predictions.itertuples()}
    # Compare identical fully-labelled test signal dates and fixed-horizon exits.
    btcfg = cfg | dict(start=str(test.date.min().date()), end=str(test.label_end.max().date()),
                       stop_loss=.999999, take_profit=1000)
    baseline_scores = {(r.symbol, str(r.date.date())): -float(r.volume_ratio) for r in predictions.itertuples()}
    latest_date = f.date.max()
    latest = f[(f.date == latest_date) & candidate_mask(f, cfg)].dropna(subset=FEATURES).copy()
    latest['score'] = model.predict_proba(latest[FEATURES])[:, 1] if len(latest) else []
    return dict(model=cfg.get('model', 'logistic'), train=dict(samples=len(train), start=str(train.date.min().date()),
                end=str(train.date.max().date()), label_end=str(train.label_end.max().date())),
                validation=vm, test=tm, config=cfg, features=FEATURES,
                ranking=latest[['symbol', 'date', 'score']].sort_values('score', ascending=False).assign(date=lambda x: x.date.dt.strftime('%Y-%m-%d')).to_dict('records'),
                backtest=backtest(frame, btcfg, scores, check), baseline=backtest(frame, btcfg, baseline_scores, check),
                note='分數未校準，僅供排序。測試回測使用固定持有期、同一完整標籤候選池，停用止賺止蝕；模型只在訓練段擬合。')
