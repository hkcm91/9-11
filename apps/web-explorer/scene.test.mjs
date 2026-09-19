import test from 'node:test';
import assert from 'node:assert/strict';
import { getSceneState, buildScene, updateSceneSources } from './scene.mjs';

const at = time => `2001-09-11T${time}-04:00`;
test('inclusive minute anchors, just-before boundaries, and reverse scrubbing', () => {
  const cases = [
    ['08:00:00', 'intact', 'intact'], ['08:45:59.999', 'intact', 'intact'],
    ['08:46:00', 'impacted', 'intact'], ['09:02:59.999', 'impacted', 'intact'],
    ['09:03:00', 'impacted', 'impacted'], ['09:58:59.999', 'impacted', 'impacted'],
    ['09:59:00', 'impacted', 'collapsed'], ['10:27:59.999', 'impacted', 'collapsed'],
    ['10:28:00', 'collapsed', 'collapsed'], ['12:00:00', 'collapsed', 'collapsed'],
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
  for (const time of ['08:00:00', '08:46:00', '09:03:00', '09:59:00', '10:28:00']) {
    const state = getSceneState(at(time)), data = buildScene(state);
    for (const tower of ['north', 'south']) {
      const solids = data.solid.features.filter(f => f.properties.tower === tower);
      assert.equal(solids.some(f => f.properties.kind === 'tower'), state[tower] !== 'collapsed');
      assert.equal(solids.some(f => f.properties.kind === 'damage'), state[tower] === 'impacted');
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
  const patches = buildScene(getSceneState(at('09:03:00'))).solid.features.filter(f => f.properties.kind === 'damage');
  for (const patch of patches) {
    const latitudes = patch.geometry.coordinates[0].map(p => p[1]);
    if (patch.properties.tower === 'north') {
      assert.ok(Math.min(...latitudes) > 40.71273);
      assert.ok(patch.properties.base >= 350 && patch.properties.height <= 377);
    } else {
      assert.ok(Math.max(...latitudes) < 40.71173);
      assert.ok(patch.properties.base >= 290 && patch.properties.height <= 324);
    }
  }
});

test('updating sources clears old effects when scrubbing backward', () => {
  const sources = {};
  const map = { getSource: id => ({ setData: data => { sources[id] = data; } }) };
  updateSceneSources(map, getSceneState(at('10:28:00')));
  assert.ok(sources['wtc-dust'].features.length);
  updateSceneSources(map, getSceneState(at('08:00:00')));
  assert.equal(sources['wtc-dust'].features.length, 0);
  assert.equal(sources['wtc-smoke'].features.length, 0);
  assert.equal(sources['historical-wtc'].features.length, 3);
});
