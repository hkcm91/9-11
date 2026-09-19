import { readFileSync } from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { getSceneState, buildScene, updateSceneSources, TOWERS, TOWER_BEARING } from './scene.mjs';

const at = time => `2001-09-11T${time}-04:00`;
test('NIST second-level anchors, just-before boundaries, and reverse scrubbing', () => {
  const cases = [
    ['08:00:00', 'intact', 'intact'], ['08:46:29.999', 'intact', 'intact'],
    ['08:46:30', 'impacted', 'intact'], ['09:02:58.999', 'impacted', 'intact'],
    ['09:02:59', 'impacted', 'impacted'], ['09:58:58.999', 'impacted', 'impacted'],
    ['09:58:59', 'impacted', 'collapsed'], ['10:28:21.999', 'impacted', 'collapsed'],
    ['10:28:22', 'collapsed', 'collapsed'], ['12:00:00', 'collapsed', 'collapsed'],
  ];
  for (const [time, north, south] of [...cases, ...cases.toReversed()]) {
    assert.deepEqual(getSceneState(at(time)), { north, south });
    assert.deepEqual(getSceneState(new Date(at(time))), { north, south });
    assert.deepEqual(getSceneState(Date.parse(at(time))), { north, south });
  }
  assert.deepEqual(getSceneState('2001-09-11T13:03:00Z'), { north: 'impacted', south: 'impacted' });
  assert.throws(() => getSceneState('invalid'), TypeError);
});

test('collapsed towers lose standing mass, antenna, damage and elevated smoke', () => {
  for (const time of ['08:00:00', '08:46:30', '09:02:59', '09:58:59', '10:28:22']) {
    const state = getSceneState(at(time)), data = buildScene(state);
    for (const tower of ['north', 'south']) {
      const solids = data.solid.features.filter(f => f.properties.tower === tower);
      assert.equal(solids.some(f => f.properties.kind === 'tower'), state[tower] !== 'collapsed');
      assert.equal(solids.some(f => f.properties.kind === 'damage'), state[tower] === 'impacted');
      assert.equal(solids.some(f => f.properties.kind === 'flame'), state[tower] === 'impacted');
      assert.equal(solids.some(f => f.properties.kind === 'debris'), state[tower] === 'collapsed');
      assert.equal(data.smoke.features.some(f => f.properties.tower === tower), state[tower] === 'impacted');
      assert.equal(data.dust.features.some(f => f.properties.tower === tower), state[tower] === 'collapsed');
    }
    assert.equal(data.solid.features.some(f => f.properties.kind === 'antenna'), state.north !== 'collapsed');
    for (const collection of [data.solid, data.smoke, data.dust]) for (const f of collection.features) {
      assert.ok(f.properties.height > f.properties.base);
      assert.deepEqual(f.geometry.coordinates[0][0], f.geometry.coordinates[0].at(-1));
    }
  }
});

test('damage is at distinct heights on north and south exterior faces', () => {
  const patches = buildScene(getSceneState(at('09:02:59'))).solid.features.filter(f => f.properties.kind === 'damage');
  for (const patch of patches) {
    const latitudes = patch.geometry.coordinates[0].map(p => p[1]);
    if (patch.properties.tower === 'north') {
      assert.ok(Math.min(...latitudes) > TOWERS[0].lat);
      assert.ok(patch.properties.base >= 350 && patch.properties.height <= 377);
    } else {
      assert.ok(Math.max(...latitudes) < TOWERS[1].lat);
      assert.ok(patch.properties.base >= 290 && patch.properties.height <= 324);
    }
  }
});

test('updating sources clears old effects when scrubbing backward', () => {
  const sources = {};
  const map = { getSource: id => ({ setData: data => { sources[id] = data; } }) };
  updateSceneSources(map, getSceneState(at('10:28:22')));
  assert.ok(sources['wtc-dust'].features.length);
  updateSceneSources(map, getSceneState(at('08:00:00')));
  assert.equal(sources['wtc-dust'].features.length, 0);
  assert.equal(sources['wtc-smoke'].features.length, 0);
  assert.equal(sources['historical-wtc'].features.length, 3);
});

test('both renderers share centers and alignment derived from the reference pools', () => {
  const reference=JSON.parse(readFileSync(new URL('./references/memorial-pools.geojson',import.meta.url),'utf8'));
  for(const feature of reference.features) {
    const tower=TOWERS.find(t=>t.id===feature.properties.tower);
    const ring=feature.geometry.coordinates[0].slice(0,-1);
    const lng=ring.reduce((sum,p)=>sum+p[0],0)/ring.length;
    const lat=ring.reduce((sum,p)=>sum+p[1],0)/ring.length;
    assert.ok(Math.abs(tower.lng-lng)<1e-7 && Math.abs(tower.lat-lat)<1e-7);
    const east=(ring[2][0]-ring[1][0])*Math.cos(lat*Math.PI/180);
    const north=ring[2][1]-ring[1][1];
    assert.ok(Math.abs(Math.atan2(north,east)*180/Math.PI-TOWER_BEARING)<.001);
  }
  assert.ok(TOWERS[1].lng>TOWERS[0].lng && TOWERS[1].lat<TOWERS[0].lat);
});
