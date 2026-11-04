export const direction = (change: number) => change > 0 ? 'up' : change < 0 ? 'down' : 'flat'
export function candleGeometry(bar: {open:number;close:number;high:number;low:number}, min:number, max:number, height:number) {
  const y = (price:number) => (max-price)/Math.max(max-min, .000001)*height
  return {direction:direction(bar.close-bar.open), top:y(Math.max(bar.open,bar.close)),
    height:Math.max(1,Math.abs(y(bar.open)-y(bar.close))), wickTop:y(bar.high),wickBottom:y(bar.low)}
}
