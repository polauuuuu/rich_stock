import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Activity, ArrowDown, ArrowDownToLine, ArrowRight, ArrowUpRight, BarChart3, Check, ChevronLeft, ChevronRight, Database, FlaskConical, Layers3, LoaderCircle, Play, RefreshCw, Search, SlidersHorizontal, Sparkles, X, CircleHelp, TrendingUp } from 'lucide-react'
import { Area, AreaChart, Bar, Brush, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { loadResult } from './result-loader'

type Source = 'demo' | 'live'
type Tab = 'scan' | 'backtest' | 'ml' | 'data'
type Row = { symbol: string; date: string; open: number; high: number; low: number; close: number; volume: number; return_3: number; return_20: number; volume_ratio: number; ma_distance: number; volatility: number; dollar_volume: number; signal: boolean }
type Coverage = { symbols: number; bars: number; start: string | null; end: string | null }
type Status = { datasets: Record<Source, Coverage>; credentials_configured: boolean; warning: string; universe: { updated: string; included: number; excluded: number } | null }
type Config = { down_days: number; volume_days: number; min_price: number; min_dollar_volume: number; holding_days: number; stop_loss: number; take_profit: number; cost_bps: number; max_positions: number; capital: number; top_k: number; start: string; end: string; model: string; symbols: string }
type Job = { id: string; kind: string; state: string; progress: number; message: string; created: string; config: { source: Source } }
type Trade = { symbol: string; entry_date: string; exit_date: string; entry_price: number; exit_price: number; qty: number; pnl: number; return_pct: number; reason: string }
type BT = { metrics: { total_return_pct: number; max_drawdown_pct: number; win_rate_pct: number; average_trade_pct: number; trades: number; open_positions: number }; equity: { date: string; equity: number }[]; trades: Trade[]; open_positions: unknown[] }
type Eval = { samples: number; start: string; end: string; positive_rate: number; pr_auc: number; roc_auc: number; top_k_hit_rate: number }
type Result = Partial<BT> & { source: Source; model?: string; train?: { samples: number; start: string; end: string; label_end: string }; validation?: Eval; test?: Eval; backtest?: BT; baseline?: BT; ranking?: { symbol: string; date: string; score: number }[]; note?: string; downloaded?: number; requested?: number; missing?: string[] }

const fmt = (n: number, digits = 2) => Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—'
const compact = (n: number) => Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
const percent = (n: number) => `${n > 0 ? '+' : ''}${fmt(n)}%`
const shortDate = (s: string) => s.slice(0, 10)
const tooltipStyle = { background: '#18222e', border: '1px solid #344353', borderRadius: 10, color: '#e6edf4', fontSize: 12 }
const labels: Record<Tab, string> = { scan: '市場掃描', backtest: '策略回測', ml: 'ML 實驗室', data: '數據管理' }
const states: Record<string, string> = { queued: '等候中', running: '執行中', cancelling: '取消中', completed: '已完成', failed: '失敗', cancelled: '已取消', interrupted: '已中斷' }

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch('/api' + url, options)
  if (!r.ok) {
    let detail: unknown = `HTTP ${r.status}`
    try { detail = (await r.json()).detail } catch { /* retain HTTP status */ }
    throw new Error(typeof detail === 'string' ? detail : '輸入格式有誤，請檢查日期及數值。')
  }
  return r.json()
}

function Field({ label, children, help }: { label: string; children: ReactNode; help?: string }) {
  return <label className="field"><span>{label}{help && <span title={help} className="help"><CircleHelp size={12} /></span>}</span>{children}</label>
}

function Stat({ label, value, sub, icon, color = '' }: { label: string; value: string; sub: string; icon: ReactNode; color?: string }) {
  return <div className="stat"><div className="stat-top">{label}<span>{icon}</span></div><div className={'stat-value ' + color}>{value}</div><div className="stat-sub">{sub}</div></div>
}

function Equity({ bt, baseline }: { bt: BT; baseline?: BT }) {
  const base = new Map(baseline?.equity.map(p => [p.date, p.equity]))
  const points = bt.equity.map(p => ({ ...p, baseline: base.get(p.date) }))
  return <div className="equity-chart"><ResponsiveContainer width="100%" height={285}><AreaChart data={points} margin={{ left: 5, right: 20, top: 20 }}>
    <defs><linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#43d6b5" stopOpacity={.25}/><stop offset="100%" stopColor="#43d6b5" stopOpacity={0}/></linearGradient></defs>
    <CartesianGrid stroke="#24303b" vertical={false}/><XAxis dataKey="date" tickFormatter={s => s.slice(0, 7)} minTickGap={70} tick={{ fill: '#80909f', fontSize: 11 }} axisLine={false} tickLine={false}/><YAxis domain={['auto', 'auto']} tickFormatter={compact} width={65} tick={{ fill: '#80909f', fontSize: 11 }} axisLine={false} tickLine={false}/><Tooltip contentStyle={tooltipStyle} formatter={(v: number) => '$' + fmt(v)} />
    <Area name="策略資產" type="monotone" dataKey="equity" stroke="#43d6b5" fill="url(#equityFill)" strokeWidth={2} isAnimationActive={false}/>{baseline && <Area name="純規則基準" dataKey="baseline" stroke="#8c92ec" fill="none" isAnimationActive={false}/>}
  </AreaChart></ResponsiveContainer></div>
}

export default function App() {
  const [tab, setTab] = useState<Tab>('scan')
  const [source, setSource] = useState<Source>('demo')
  const [status, setStatus] = useState<Status | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [bars, setBars] = useState<Row[]>([])
  const [selected, setSelected] = useState('')
  const [asOf, setAsOf] = useState('')
  const [effective, setEffective] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ key: keyof Row; asc: boolean }>({ key: 'volume_ratio', asc: true })
  const [page, setPage] = useState(0)
  const [busy, setBusy] = useState(false)
  const [chartBusy, setChartBusy] = useState(false)
  const [error, setError] = useState('')
  const [jobs, setJobs] = useState<Job[]>([])
  const [result, setResult] = useState<Result | null>(null)
  const [resultId, setResultId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [cfg, setCfg] = useState<Config>({ down_days: 3, volume_days: 3, min_price: 5, min_dollar_volume: 1000000, holding_days: 5, stop_loss: .05, take_profit: .1, cost_bps: 10, max_positions: 5, capital: 100000, top_k: 5, start: '2020-01-01', end: '2026-11-03', model: 'logistic', symbols: '' })
  const [scanCfg, setScanCfg] = useState(cfg)
  const scanRequest = useRef(0)
  const loadedResults = useRef(new Set<string>())
  const inflightResults = useRef(new Set<string>())
  const pendingJob = useRef<Job | null>(null)
  const update = <K extends keyof Config>(key: K, value: Config[K]) => setCfg(c => ({ ...c, [key]: value }))
  const numberInput = (key: keyof Config, min = 0, step = 1, multiplier = 1) => <input type="number" min={min} step={step} value={Number(cfg[key]) * multiplier} onChange={e => update(key, Number(e.target.value) / multiplier as never)} />
  const scanParams = (config = scanCfg) => new URLSearchParams({ source, down_days: String(config.down_days), volume_days: String(config.volume_days), min_price: String(config.min_price), min_dollar_volume: String(config.min_dollar_volume), ...(asOf ? { as_of: asOf } : {}) })

  async function refreshStatus() { setStatus(await api<Status>('/status')) }
  async function scan(config = cfg) {
    const id = ++scanRequest.current
    setBusy(true); setError(''); setPage(0); setResult(null)
    try {
      const data = await api<{ rows: Row[]; as_of: string }>('/scan?' + scanParams(config))
      if (id !== scanRequest.current) return
      setRows(data.rows); setEffective(data.as_of); setScanCfg(config)
      setSelected(previous => data.rows.some(r => r.symbol === previous) ? previous : data.rows[0]?.symbol || '')
    } catch (e) { if (id === scanRequest.current) { setError((e as Error).message); setRows([]); setSelected(''); setBars([]) } }
    finally { if (id === scanRequest.current) setBusy(false) }
  }

  useEffect(() => { refreshStatus().catch(e => setError(e.message)) }, [])
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }) }, [tab])
  useEffect(() => {
    setResult(null); setResultId(''); setRows([]); setBars([]); setSelected(''); scan(cfg)
    if (pendingJob.current?.config.source === source) {
      setResultId(pendingJob.current.id)
      pendingJob.current = null
    }
  }, [source]) // applied filters refresh on explicit scan
  useEffect(() => {
    let active = true
    if (!selected) { setBars([]); return }
    setChartBusy(true)
    const params = new URLSearchParams({ source, down_days: String(scanCfg.down_days), volume_days: String(scanCfg.volume_days), ...(effective ? { as_of: effective } : {}) })
    api<{ bars: Row[] }>('/bars/' + encodeURIComponent(selected) + '?' + params).then(r => { if (active) setBars(r.bars) }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setChartBusy(false) })
    return () => { active = false }
  }, [selected, source, effective, scanCfg])
  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const all = await api<Job[]>('/jobs')
        if (!active) return
        setJobs(all)
        const done = all.find(j => j.id === resultId && j.state === 'completed')
        if (done) {
          await loadResult(done.id, loadedResults.current, inflightResults.current,
            () => api<Result>('/results/' + done.id), data => {
              if (!active) return false
              setResult(data); refreshStatus().catch(() => {}); return true
            })
        }
      } catch (e) { if (active) setError((e as Error).message) }
    }
    poll(); const timer = setInterval(poll, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [resultId])

  async function submit(kind: string) {
    setSubmitting(true); setError(''); setResult(null)
    try {
      const config: Record<string, unknown> = { ...cfg, source: kind === 'download' ? 'live' : source, kind }
      if (!cfg.start) delete config.start
      if (!cfg.end) delete config.end
      const data = await api<{ id: string }>('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) })
      setResultId(data.id); loadedResults.current.delete(data.id)
      setJobs(await api<Job[]>('/jobs'))
    } catch (e) { setError((e as Error).message) } finally { setSubmitting(false) }
  }

  const coverage = status?.datasets[source]
  const activeJob = jobs.find(j => ['running', 'queued', 'cancelling'].includes(j.state))
  const currentJob = jobs.find(j => j.id === resultId)
  const filtered = rows.filter(r => r.symbol.toLowerCase().includes(query.toLowerCase())).sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key]
    const cmp = typeof av === 'string' ? av.localeCompare(String(bv)) : Number(av) - Number(bv)
    return sort.asc ? cmp : -cmp
  })
  const selectedRow = rows.find(r => r.symbol === selected)
  const changeSort = (key: keyof Row) => setSort(s => ({ key, asc: s.key === key ? !s.asc : true }))
  const nav = [{ key: 'scan' as Tab, icon: <Layers3 size={19}/>, name: '市場掃描', sub: 'Market scanner' }, { key: 'backtest' as Tab, icon: <BarChart3 size={19}/>, name: '策略回測', sub: 'Backtesting' }, { key: 'ml' as Tab, icon: <FlaskConical size={19}/>, name: 'ML 實驗室', sub: 'Machine learning' }, { key: 'data' as Tab, icon: <Database size={19}/>, name: '數據管理', sub: 'Data workspace' }]
  const validResult = result?.source === source || tab === 'data' ? result : null
  const bt = tab === 'ml' ? validResult?.backtest : validResult?.metrics ? validResult as BT : undefined

  return <div className="app-shell">
    <aside className="sidebar"><a href="#" className="brand" onClick={e => { e.preventDefault(); setTab('scan') }}><div className="brand-mark"><TrendingUp size={23}/></div><div>rich<span>stock</span><small>RESEARCH WORKSPACE</small></div></a>
      <div className="workspace-label">工作空間 <span>PERSONAL</span></div>
      <nav aria-label="主選單">{nav.map(n => <button key={n.key} className={'nav-item ' + (tab === n.key ? 'active' : '')} onClick={() => { setTab(n.key); setError(''); setResult(null); setResultId('') }}>{n.icon}<span>{n.name}<small>{n.sub}</small></span>{tab === n.key && <span className="nav-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="research-note"><Sparkles size={18}/><strong>由訊號，到證據。</strong><p>先驗證規則，再讓模型幫你排序。</p><span>研究工具 · 不執行交易</span></div><div className="profile"><div className="avatar">R</div><div>個人研究空間<small>Local workspace</small></div><span className="online-dot"/></div></div>
    </aside>
    <main><header className="topbar"><div className="breadcrumb">工作空間 <ChevronRight size={13}/> <span>{labels[tab]}</span></div><div className="top-actions"><span className="local-status"><span className="online-dot"/>本機運行</span><div className="source-switch" aria-label="資料來源"><button className={source === 'demo' ? 'selected' : ''} onClick={() => setSource('demo')}>示範模式</button><button className={source === 'live' ? 'selected' : ''} onClick={() => setSource('live')}>Alpaca SIP</button></div></div></header>
      <div className="content"><div className="page-heading"><div><div className="eyebrow">{tab === 'scan' ? 'DISCOVER THE NEXT SETUP' : tab === 'backtest' ? 'TEST BEFORE YOU TRUST' : tab === 'ml' ? 'EVIDENCE OVER INTUITION' : 'YOUR RESEARCH FOUNDATION'}</div><h1>{labels[tab]}<span className="beta">RESEARCH</span></h1><p>{tab === 'scan' ? '捕捉連跌縮量形態，尋找值得進一步研究的回調機會。' : tab === 'backtest' ? '將交易假設放進歷史，觀察成本、回撤與真正的持倉結果。' : tab === 'ml' ? '以時間切分驗證，研究模型能否超越純規則篩選。' : '管理股票池、歷史日線及下載工作，讓每個結果都有依據。'}</p></div><button className="button secondary" onClick={() => { refreshStatus().catch(e => setError(e.message)); if (tab === 'scan') scan() }}><RefreshCw size={15}/>重新整理</button></div>
        <div className={'source-banner ' + (source === 'demo' ? 'demo' : 'live')}><div><span className="banner-dot"/><strong>{source === 'demo' ? '合成示範數據' : 'Alpaca · SIP 歷史數據'}</strong><span>{source === 'demo' ? '股票代號僅作介面示範，價量並非真實歷史，績效不代表策略有效。' : '使用目前上市名單，有生存者偏差；價格及成交量採拆股調整。'}</span></div><span className="banner-tag">{source === 'demo' ? 'DEMO DATA' : 'HISTORICAL'}</span></div>
        {error && <div className="error" role="alert"><span>{error}</span><button aria-label="關閉錯誤" onClick={() => setError('')}><X size={16}/></button></div>}
        {activeJob && <div className="job-banner"><LoaderCircle size={17} className="spin"/><div><strong>{states[activeJob.state]} · {activeJob.kind === 'train' ? '模型實驗' : activeJob.kind === 'download' ? '數據下載' : '策略回測'}</strong><small>{activeJob.message}</small><progress max={1} value={activeJob.progress}/></div><button className="button secondary small" disabled={activeJob.state === 'cancelling'} onClick={() => api('/jobs/' + activeJob.id + '/cancel', { method: 'POST' }).catch(e => setError(e.message))}>取消</button></div>}
        {currentJob && ['failed', 'cancelled', 'interrupted'].includes(currentJob.state) && <div className="error" role="status">{states[currentJob.state]}：{currentJob.message}</div>}

        {tab === 'scan' && <>
          <section className="stats-grid"><Stat label="研究股票池" value={compact(coverage?.symbols || 0)} sub="隻股票 · 當前資料覆蓋" icon={<Database size={17}/>}/><Stat label="符合形態" value={busy ? '…' : String(rows.length).padStart(2, '0')} sub={`截至 ${effective || '—'} · 已套用篩選`} icon={<Layers3 size={17}/>} color="teal"/><Stat label="平均三日跌幅" value={rows.length ? percent(rows.reduce((s, r) => s + r.return_3, 0) / rows.length * 100) : '—'} sub="候選股的收市價變動" icon={<ArrowDown size={17}/>} color="red"/><Stat label="平均相對成交量" value={rows.length ? fmt(rows.reduce((s, r) => s + r.volume_ratio, 0) / rows.length) + '×' : '—'} sub="當日成交量 ÷ 20 日平均" icon={<Activity size={17}/>}/></section>
          <section className="panel filter-panel"><div className="section-title"><SlidersHorizontal size={17}/><h2>掃描條件</h2><span>以收市價確認形態</span></div><form onSubmit={e => { e.preventDefault(); scan() }} className="filter-fields"><Field label="截至日期"><input type="date" value={asOf} max={coverage?.end || undefined} onChange={e => setAsOf(e.target.value)} aria-label="截至日期"/></Field><Field label="連續下跌" help="3 日下跌需要 4 個連續交易日收市價">{numberInput('down_days', 1)}<span className="input-unit">日</span></Field><Field label="成交量遞減">{numberInput('volume_days', 1)}<span className="input-unit">日</span></Field><Field label="最低股價 (USD)">{numberInput('min_price', 0, .5)}</Field><Field label="最低平均成交金額">{numberInput('min_dollar_volume', 0, 100000)}</Field><button type="submit" className="button primary" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin"/> : <Search size={16}/>}掃描市場</button></form></section>
          <div className="scan-grid"><section className="panel results-panel"><div className="panel-header"><div><h2>候選股票 <span className="count">{filtered.length}</span></h2><p>縮量形態是研究起點，並非買入訊號</p></div><a className="icon-button" title="匯出已套用條件的完整候選清單" aria-label="匯出 CSV" href={'/api/export?' + new URLSearchParams({ ...Object.fromEntries(scanParams()), ...(effective ? { as_of: effective } : {}) })}><ArrowDownToLine size={17}/></a></div><div className="table-toolbar"><div className="search-input"><Search size={15}/><input placeholder="搜尋股票代號…" aria-label="搜尋股票代號" value={query} onChange={e => { setQuery(e.target.value); setPage(0) }}/></div><span>按欄位排序 <ArrowDown size={12}/></span></div>
            <div className="table-scroll"><table><thead><tr>{([['symbol', '股票'], ['close', '收市價'], ['return_3', '三日變動'], ['volume_ratio', '相對量']] as [keyof Row, string][]).map(([key, label]) => <th key={key}><button onClick={() => changeSort(key)}>{label}{sort.key === key && <span>{sort.asc ? ' ↑' : ' ↓'}</span>}</button></th>)}<th/></tr></thead><tbody>{filtered.slice(page * 8, page * 8 + 8).map((r, i) => <tr key={r.symbol} className={selected === r.symbol ? 'selected-row' : ''} onClick={() => setSelected(r.symbol)}><td><button className="ticker-cell" onClick={() => setSelected(r.symbol)}><span className={'ticker-avatar avatar-' + i % 4}>{r.symbol.slice(0, 1)}</span><span><strong>{r.symbol}</strong><small>US EQUITY</small></span></button></td><td className="numeric">${fmt(r.close)}</td><td className="numeric red">{percent(r.return_3 * 100)}</td><td className="numeric"><span className="volume-pill">{fmt(r.volume_ratio)}×</span></td><td><ChevronRight size={15}/></td></tr>)}</tbody></table>{!rows.length && <div className="empty"><Search size={27}/><strong>{busy ? '正在掃描…' : '暫時冇符合條件嘅股票'}</strong><p>試吓放寬條件，或到數據管理下載歷史資料。</p></div>}</div><div className="table-footer"><span>{filtered.length ? page * 8 + 1 : 0}–{Math.min(page * 8 + 8, filtered.length)} / {filtered.length} 隻</span><div><button className="icon-button" aria-label="上一頁" disabled={page === 0} onClick={() => setPage(p => p - 1)}><ChevronLeft size={16}/></button><button className="icon-button" aria-label="下一頁" disabled={(page + 1) * 8 >= filtered.length} onClick={() => setPage(p => p + 1)}><ChevronRight size={16}/></button></div></div></section>
            <section className="panel stock-panel"><div className="panel-header"><div><div className="stock-title"><span className="stock-icon">{selected.slice(0, 1) || 'R'}</span><h2>{selected || '選擇股票'}</h2><span className="badge">日線</span></div><p>{selected ? '最近 300 個交易日 · 拖曳底部範圍探索' : '點選候選股票，查看價量走勢'}</p></div><span className="subtle"><Activity size={16}/></span></div><div className="stock-price">{selectedRow ? '$' + fmt(selectedRow.close) : '—'}<span className="red">{selectedRow && percent(selectedRow.return_3 * 100)}<small>三日</small></span></div><div className="chart-legend"><span><i className="teal-dot"/>收市價</span><span><i className="purple-dot"/>成交量</span><span className="subtle">{chartBusy ? '載入中…' : effective}</span></div>
              <div className="price-chart"><ResponsiveContainer width="100%" height={275}><ComposedChart data={bars.map(r => ({ ...r, date: shortDate(r.date) }))} margin={{ left: -15, right: 8, top: 12 }}><CartesianGrid stroke="#24303b" vertical={false}/><XAxis dataKey="date" tickFormatter={s => s.slice(5)} tick={{ fill: '#81909d', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={45}/><YAxis yAxisId="price" domain={['auto', 'auto']} tickFormatter={v => fmt(v, 0)} tick={{ fill: '#81909d', fontSize: 10 }} axisLine={false} tickLine={false}/><YAxis yAxisId="volume" hide domain={[0, (max: number) => max * 5]}/><Tooltip contentStyle={tooltipStyle} formatter={(v: number, name: string) => name === '成交量' ? compact(v) : '$' + fmt(v)}/><Bar yAxisId="volume" name="成交量" dataKey="volume" fill="#555c89" opacity={.45} isAnimationActive={false}/><Line yAxisId="price" name="收市價" type="monotone" dataKey="close" stroke="#43d6b5" dot={false} strokeWidth={2} isAnimationActive={false}/><Brush dataKey="date" height={22} stroke="#34444e" fill="#101923" tickFormatter={s => s.slice(5)} travellerWidth={7} startIndex={Math.max(0, bars.length - 90)}/></ComposedChart></ResponsiveContainer></div>
              <div className="stock-details"><div><span>當日成交量</span><strong>{selectedRow ? compact(selectedRow.volume) : '—'}</strong></div><div><span>20 日平均成交金額</span><strong>{selectedRow ? '$' + compact(selectedRow.dollar_volume) : '—'}</strong></div><div><span>相對 20 日均線</span><strong>{selectedRow ? percent(selectedRow.ma_distance * 100) : '—'}</strong></div></div><div className="setup-note"><span><Check size={14}/></span><div><strong>連跌 {scanCfg.down_days} 日 · 縮量 {scanCfg.volume_days} 日</strong><p>沽壓可能減弱，亦可能缺乏買盤。用回測檢驗下一步。</p></div></div><button className="text-button" onClick={() => { setTab('backtest'); setResult(null); setResultId('') }}>研究呢個形態 <ArrowRight size={15}/></button></section></div>
          <section className="method-strip"><div className="method-icon"><FlaskConical size={20}/></div><div><strong>一個形態，一個可以驗證嘅假設。</strong><p>掃描 → 下一交易日入場 → 計入成本 → 樣本外驗證</p></div><button className="button secondary small" onClick={() => setTab('ml')}>探索 ML 實驗室 <ArrowUpRight size={14}/></button></section>
        </>}

        {(tab === 'backtest' || tab === 'ml') && <>
          <div className="experiment-grid"><section className="panel experiment-form"><div className="panel-header"><div><h2>{tab === 'ml' ? '模型實驗設定' : '策略參數'}</h2><p>使用全股票池，掃描條件沿用目前設定。</p></div><FlaskConical size={19}/></div><form onSubmit={e => { e.preventDefault(); submit(tab === 'ml' ? 'train' : 'backtest') }}><div className="form-grid"><Field label="開始日期"><input type="date" required value={cfg.start} onChange={e => update('start', e.target.value)}/></Field><Field label="結束日期"><input type="date" required value={cfg.end} onChange={e => update('end', e.target.value)}/></Field><Field label="連續下跌日數">{numberInput('down_days', 1)}</Field><Field label="縮量日數">{numberInput('volume_days', 1)}</Field><Field label="最低股價 (USD)">{numberInput('min_price', 0, 1)}</Field><Field label="最低平均成交金額">{numberInput('min_dollar_volume', 0, 100000)}</Field><Field label="持有交易日數">{numberInput('holding_days', 1)}</Field><Field label="每邊成本 (bps)" help="包含手續費、差價及滑價的合併假設">{numberInput('cost_bps', 0)}</Field><Field label="起始資金 (USD)">{numberInput('capital', 100, 100)}</Field><Field label="持倉上限">{numberInput('max_positions', 1)}</Field><Field label="每日最多候選股">{numberInput('top_k', 1)}</Field>{tab === 'ml' ? <Field label="模型"><select value={cfg.model} onChange={e => update('model', e.target.value)}><option value="logistic">Logistic Regression</option><option value="tree">Gradient Boosting</option></select></Field> : <><Field label="止蝕 (%)">{numberInput('stop_loss', .1, .1, 100)}</Field><Field label="止賺 (%)">{numberInput('take_profit', .1, .1, 100)}</Field></>}</div><div className="form-note">{tab === 'ml' ? '標籤：固定持有期扣成本後是否正回報。60% 訓練、20% 驗證、20% 測試，清除跨分界標籤；比較回測停用止賺止蝕。' : '收市確認訊號，下一交易日開市買入；同日觸及止賺及止蝕時，先計止蝕。資金等額分配，不重複持有。'}</div><button className="button primary full" disabled={submitting || !!activeJob}><Play size={16}/>{tab === 'ml' ? '訓練並驗證模型' : '執行歷史回測'}</button></form></section>
            <section className="experiment-results">{bt ? <><div className="stats-grid result-stats"><Stat label="組合回報" value={percent(bt.metrics.total_return_pct)} sub="包含未平倉市值及已扣成本" icon={<TrendingUp size={16}/>} color={bt.metrics.total_return_pct >= 0 ? 'teal' : 'red'}/><Stat label="最大回撤" value={percent(bt.metrics.max_drawdown_pct)} sub="資產曲線最高點至低點" icon={<ArrowDown size={16}/>} color="red"/><Stat label="已平倉交易" value={String(bt.metrics.trades)} sub={`勝率 ${fmt(bt.metrics.win_rate_pct, 1)}% · 未平倉 ${bt.metrics.open_positions}`} icon={<Activity size={16}/>}/></div><div className="panel"><div className="panel-header"><div><h2>資產曲線</h2><p>{tab === 'ml' ? '綠：模型排序 · 紫：同測試候選池的純規則基準' : '按實際資金限制模擬 · 未平倉以最後報價估值'}</p></div></div><Equity bt={bt} baseline={tab === 'ml' ? validResult?.baseline : undefined}/></div></> : <div className="panel experiment-empty"><div className="experiment-illustration"><FlaskConical size={38}/></div><span className="eyebrow">BUILD YOUR EVIDENCE</span><h2>{tab === 'ml' ? '模型嘅價值，交畀樣本外數據回答。' : '由一個假設，開始一次實驗。'}</h2><p>設定左邊參數並執行，結果會保存喺本機。<br/>你亦可以從下方工作紀錄開啟之前嘅研究。</p><div className="timeline"><span>設定</span><i/><span>計算</span><i/><span>驗證</span></div></div>}
              {tab === 'ml' && validResult?.test && <div className="panel ml-summary"><div className="panel-header"><div><h2>樣本外驗證</h2><p>模型只見過訓練段；分數未校準，僅作排名。</p></div><span className="badge">{validResult.model}</span></div><div className="split-bar"><span>TRAIN 60%</span><span>VAL 20%</span><span>TEST 20%</span></div><div className="evaluation-grid">{([['訓練', validResult.train], ['驗證', validResult.validation], ['測試', validResult.test]] as const).map(([name, e]) => e && <div key={name}><strong>{name} · {e.samples} 筆</strong><small>{e.start} → {e.end}</small>{'pr_auc' in e && <><p>PR-AUC <b>{fmt(e.pr_auc, 3)}</b></p><p>正例基準 <b>{fmt(e.positive_rate * 100, 1)}%</b></p><p>Top-K 命中率 <b>{fmt(e.top_k_hit_rate * 100, 1)}%</b></p></>}</div>)}</div><p className="form-note">{validResult.note}</p>{!!validResult.ranking?.length && <div className="ranking"><strong>最新候選排名 · 未校準分數</strong>{validResult.ranking.map((r, i) => <div key={r.symbol}><span>{i + 1}. {r.symbol}</span><span>{shortDate(r.date)}</span><b>{fmt(r.score, 3)}</b></div>)}</div>}</div>}
            </section></div>
          {bt && <section className="panel trade-panel"><div className="panel-header"><div><h2>已平倉交易</h2><p>展示最近 100 筆 · {bt.open_positions.length} 個未平倉持倉未計入交易勝率</p></div></div><div className="table-scroll"><table><thead><tr><th>股票</th><th>買入日期</th><th>賣出日期</th><th>入場價</th><th>離場價</th><th>股數</th><th>扣成本回報</th><th>離場原因</th></tr></thead><tbody>{bt.trades.slice(-100).reverse().map((t, i) => <tr key={i}><td><strong>{t.symbol}</strong></td><td>{t.entry_date}</td><td>{t.exit_date}</td><td>${fmt(t.entry_price)}</td><td>${fmt(t.exit_price)}</td><td>{t.qty}</td><td className={t.return_pct >= 0 ? 'teal' : 'red'}>{percent(t.return_pct)}</td><td>{t.reason}</td></tr>)}</tbody></table>{!bt.trades.length && <div className="empty">所選期間冇已平倉交易，請檢查篩選條件及日期。</div>}</div></section>}
        </>}

        {tab === 'data' && <><section className="stats-grid"><Stat label="真實股票數目" value={compact(status?.datasets.live.symbols || 0)} sub="已成功保存嘅股票日線" icon={<Database size={17}/>}/><Stat label="真實日線記錄" value={compact(status?.datasets.live.bars || 0)} sub="Alpaca SIP · split-adjusted" icon={<Layers3 size={17}/>}/><Stat label="上市名單" value={status?.universe ? compact(status.universe.included) : '未下載'} sub={status?.universe ? `已排除 ${status.universe.excluded} 項 ETF／非普通股等` : 'Nasdaq Trader 官方目錄'} icon={<Activity size={17}/>}/><Stat label="API 設定" value={status?.credentials_configured ? '已設定' : '未設定'} sub="憑證只喺後端環境變數保存" icon={<Check size={17}/>} color={status?.credentials_configured ? 'teal' : ''}/></section><div className="data-grid"><section className="panel"><div className="panel-header"><div><h2>下載歷史日線</h2><p>Nasdaq Trader 股票池 + Alpaca SIP 批量 bars</p></div><ArrowDownToLine size={19}/></div><form className="data-form" onSubmit={e => { e.preventDefault(); submit('download') }}><div className="form-grid"><Field label="開始日期"><input type="date" required value={cfg.start} onChange={e => update('start', e.target.value)}/></Field><Field label="結束日期"><input type="date" required value={cfg.end} onChange={e => update('end', e.target.value)}/></Field></div><Field label="指定股票（留空掃描整個上市名單）"><input placeholder="AAPL,MSFT,NVDA" value={cfg.symbols} onChange={e => update('symbols', e.target.value)}/></Field><div className="form-note">建議先以幾隻股票測試 API。下載會排除未結束交易日，分頁讀齊所有股票，限速及錯誤會自動重試。拆股調整資料更新時會重新抓取已保存期間，避免舊價格同新價格單位不一致。</div><button className="button primary" disabled={submitting || !!activeJob}><ArrowDownToLine size={16}/>下載／更新真實數據</button></form></section><section className="panel data-guide"><h2>接通你嘅數據來源</h2><ol><li><span>01</span><div><strong>設定 Alpaca 憑證</strong><p>複製 .env.example 為 .env，填入 API key 及 secret。請勿將憑證提交到 Git。</p></div></li><li><span>02</span><div><strong>重新啟動 Docker 服務</strong><p>後端會讀取環境變數；前端只顯示「已設定」，唔會接觸 key。</p></div></li><li><span>03</span><div><strong>下載並切換至 Alpaca SIP</strong><p>先下載一年測試流程，研究時再擴展至多個年份。免費歷史 SIP 保留最近 15 分鐘限制。</p></div></li></ol><div className="coverage-line">真實數據覆蓋 <strong>{status?.datasets.live.start || '—'} → {status?.datasets.live.end || '—'}</strong></div></section></div>{validResult?.downloaded !== undefined && <div className="panel download-result"><h2>下載結果：{validResult.downloaded} / {validResult.requested} 隻成功</h2><p>未返回數據：{validResult.missing?.join(', ') || '無'}</p><p>{validResult.note}</p></div>}</>}

        {tab !== 'scan' && <section className="panel jobs-panel"><div className="panel-header"><div><h2>研究工作紀錄</h2><p>保存最近 40 項工作 · 點選完成項目查看結果</p></div><Database size={17}/></div>{jobs.length ? <div className="table-scroll"><table><thead><tr><th>工作</th><th>來源</th><th>建立時間</th><th>狀態</th><th>訊息</th><th/></tr></thead><tbody>{jobs.map(j => <tr key={j.id}><td>{j.kind === 'train' ? '模型訓練' : j.kind === 'download' ? '數據下載' : '歷史回測'}</td><td>{j.config.source === 'demo' ? '示範' : 'SIP'}</td><td>{new Date(j.created).toLocaleString('zh-HK')}</td><td><span className={'job-state ' + j.state}>{states[j.state]}</span></td><td className="message-cell" title={j.message}>{j.message}</td><td>{j.state === 'completed' && <button className="text-button" onClick={() => { setError(''); setResult(null); loadedResults.current.delete(j.id); setTab(j.kind === 'train' ? 'ml' : j.kind === 'download' ? 'data' : 'backtest'); if (source !== j.config.source) { pendingJob.current = j; setSource(j.config.source) } else setResultId(j.id) }}>查看 <ArrowRight size={14}/></button>}</td></tr>)}</tbody></table></div> : <div className="empty">仲未有研究工作。設定參數，開始第一個實驗。</div>}</section>}
        <footer><span><span className="online-dot"/> Rich Stock Research</span><span>歷史結果不代表未來表現 · 日線無法還原日內成交先後 · {source === 'demo' ? '合成示範' : '當前股票池存在生存者偏差'}</span></footer>
      </div>
    </main>
  </div>
}
