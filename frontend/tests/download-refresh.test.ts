import {test} from 'node:test'
import assert from 'node:assert/strict'
import {completedDownloads} from '../src/download-refresh.ts'

test('refresh only when a download transitions to completed, once',()=>{
  const seen=new Map<string,string>()
  assert.deepEqual(completedDownloads([{id:'old',kind:'download',state:'completed'}],seen),[])
  assert.deepEqual(completedDownloads([{id:'new',kind:'download',state:'running'}],seen),[])
  assert.deepEqual(completedDownloads([{id:'new',kind:'download',state:'completed'}],seen),['new'])
  assert.deepEqual(completedDownloads([{id:'new',kind:'download',state:'completed'}],seen),[])
})
test('failed and cancelled downloads never trigger chart refresh',()=>{
  const seen=new Map([['a','running'],['b','running'],['c','running']])
  assert.deepEqual(completedDownloads([{id:'a',kind:'download',state:'failed'},{id:'b',kind:'download',state:'cancelled'},{id:'c',kind:'train',state:'completed'}],seen),[])
})
