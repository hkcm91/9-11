import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { indexOrdering } from './ordering.mjs';

test('minute navigation excludes uncertain matches, ranges and absent parents', () => {
  const items = [{id:'camera', time:null, location:{latitude:40.7}}];
  const before = JSON.stringify(items);
  const assets = ['source_reported_minute', 'anchor_match_needs_review', 'range_only'].map((status, n) => ({asset_id:String(n), parent_id:'camera',status,candidate_minutes:['2001-09-11T09:03:00-04:00']}));
  assets.push({...assets[0], asset_id:'missing', parent_id:'absent'});
  const index = indexOrdering({assets}, items);
  assert.deepEqual([...index.minutes.values()].flat().map(a=>a.asset_id), ['0']);
  assert.equal(index.byParent.get('camera').length,3);
  assert.equal(JSON.stringify(items),before, 'indexing never changes capture times or coordinates');
  assert.equal(indexOrdering({assets}, items, {start:'2001-09-11T10:00:00-04:00',end:'2001-09-11T12:00:00-04:00'}).minutes.size,0);
});

test('published pilot preserves uncertain matches and individual attachment identities', () => {
  const data = JSON.parse(readFileSync(new URL('./ordering.json', import.meta.url)));
  assert.equal(data.anchors.length,5);
  assert.equal(data.assets.filter(a=>a.status==='source_reported_minute').length,80);
  assert.equal(data.assets.filter(a=>a.status==='anchor_match_needs_review').length,2);
  const ids = new Set(data.assets.map(a=>a.asset_id));
  assert.equal(ids.size,data.assets.length);
  for (const sequence of data.sequences) for (const id of sequence.asset_ids) assert.ok(ids.has(id));
  assert.ok(data.assets.every(a=>a.review_status!=='verified'));
});
