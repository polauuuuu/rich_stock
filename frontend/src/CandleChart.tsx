import {useEffect,useState} from 'react'
import {candleGeometry, direction} from './market'

type Bar = {date:string;open:number;high:number;low:number;close:number;volume:number}
const format = (v:number) => v.toLocaleString('en-US',{maximumFractionDigits:2})
export default function CandleChart({bars}:{bars:Bar[]}) {
  const [range,setRange] = useState<[number,number]>([Math.max(0,bars.length-60),bars.length-1])
  const [hover,setHover] = useState<number|null>(null)
  useEffect(()=>{setRange([Math.max(0,bars.length-60),bars.length-1]);setHover(null)},[bars])
  if(!bars.length) return <div className="empty">選擇股票以查看 K 線。</div>
  const start=Math.min(range[0],bars.length-1),end=Math.max(start,Math.min(range[1],bars.length-1))
  const data=bars.slice(start,end+1)
  const low=Math.min(...data.map(b=>b.low)),high=Math.max(...data.map(b=>b.high))
  const padding=Math.max((high-low)*.07,high*.001),min=low-padding,max=high+padding
  const width=800,height=230,left=12,top=12,plotWidth=720,step=plotWidth/data.length
  const maxVolume=Math.max(...data.map(b=>b.volume),1)
  const active=data[Math.min(hover??data.length-1,data.length-1)]
  const reset=(n:number)=>{setRange([Math.max(0,bars.length-n),bars.length-1]);setHover(null)}
  const onMove=(event:React.PointerEvent<SVGSVGElement>)=>{
    const rect=event.currentTarget.getBoundingClientRect()
    setHover(Math.max(0,Math.min(data.length-1,Math.floor(((event.clientX-rect.left)/rect.width*width-left)/step))))
  }
  return <div className="candlestick-chart">
    <div className="candle-toolbar"><span><i className="up-key"/>升 <i className="down-key"/>跌 <small>收市對比開市</small></span><div>{[30,60,120,bars.length].map((n,i)=><button key={i} type="button" className={data.length===Math.min(n,bars.length)?'active':''} onClick={()=>reset(n)}>{i===3?'全部':n+'日'}</button>)}</div></div>
    <div className={'ohlc-readout '+direction(active.close-active.open)}><strong>{active.date.slice(0,10)}</strong><span>開 {format(active.open)}</span><span>高 {format(active.high)}</span><span>低 {format(active.low)}</span><span>收 {format(active.close)}</span><span>量 {Intl.NumberFormat('en-US',{notation:'compact'}).format(active.volume)}</span></div>
    <svg viewBox={`0 0 ${width} 350`} role="img" aria-label="互動日線 K 線及成交量圖：綠色收市高於開市，紅色收市低於開市" onPointerMove={onMove} onPointerLeave={()=>setHover(null)}>
      {[0,1,2,3,4].map(i=><g key={i}><line className="candle-grid" x1={left} x2={left+plotWidth} y1={top+i*height/4} y2={top+i*height/4}/><text x={left+plotWidth+9} y={top+i*height/4+4}>{format(max-(max-min)*i/4)}</text></g>)}
      {data.map((b,i)=>{const g=candleGeometry(b,min,max,height),x=left+(i+.5)*step,w=Math.max(1,Math.min(15,step*.65));return <g key={b.date} className={'candle '+g.direction}>
        <line x1={x} x2={x} y1={top+g.wickTop} y2={top+g.wickBottom} strokeWidth={Math.max(1,Math.min(2,w/3))}/>
        <rect x={x-w/2} y={top+g.top} width={w} height={g.height}/>
        <rect className="candle-volume" x={x-w/2} y={310-b.volume/maxVolume*48} width={w} height={Math.max(1,b.volume/maxVolume*48)}/>
      </g>})}
      <text x={left} y={260}>成交量</text>
      {[0,1,2,3,4].map(i=>{const j=Math.round((data.length-1)*i/4);return <text key={i} x={left+(j+.5)*step} y={334} textAnchor="middle">{data[j].date.slice(5,10)}</text>})}
      {hover!==null&&<line className="candle-crosshair" x1={left+(Math.min(hover,data.length-1)+.5)*step} x2={left+(Math.min(hover,data.length-1)+.5)*step} y1={top} y2={312}/>}
    </svg>
    <div className="candle-range"><label>開始<input aria-label="K 線開始位置" type="range" min={0} max={bars.length-1} value={start} onChange={e=>{setRange([Math.min(+e.target.value,end),end]);setHover(null)}}/></label><label>結束<input aria-label="K 線結束位置" type="range" min={0} max={bars.length-1} value={end} onChange={e=>{setRange([start,Math.max(start,+e.target.value)]);setHover(null)}}/></label></div>
    <div className="candle-range-caption">{data[0].date.slice(0,10)} → {data[data.length-1].date.slice(0,10)} · {data.length} 個交易日</div>
  </div>
}
