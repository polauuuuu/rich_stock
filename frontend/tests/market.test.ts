import {test} from 'node:test'
import assert from 'node:assert/strict'
import {direction, candleGeometry} from '../src/market.ts'

test('positive returns are green, negatives red, unchanged neutral', () => {
  assert.equal(direction(1), 'up')
  assert.equal(direction(-1), 'down')
  assert.equal(direction(0), 'flat')
})
test('candle body uses open and close, wick uses high and low', () => {
  const c = candleGeometry({open:10,close:12,high:14,low:8}, 8, 14, 180)
  assert.equal(c.direction, 'up')
  assert.equal(c.wickTop, 0)
  assert.equal(c.wickBottom, 180)
  assert.equal(c.top, 60)
  assert.equal(c.height, 60)
  assert.equal(candleGeometry({open:12,close:10,high:14,low:8},8,14,180).direction,'down')
})
