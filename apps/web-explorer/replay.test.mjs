import test from 'node:test';
import assert from 'node:assert/strict';
import { SOUTH_COLLAPSE, sampleReplay, sampleSouthPose, smokeParticle } from './replay.mjs';

test('South sequence is bounded; North retains its later transition', () => {
  assert.equal(sampleReplay(SOUTH_COLLAPSE-1).south.status,'impacted');
  assert.equal(sampleReplay(SOUTH_COLLAPSE).south.status,'collapsing');
  assert.equal(sampleReplay(SOUTH_COLLAPSE+11999).south.status,'collapsing');
  assert.equal(sampleReplay(SOUTH_COLLAPSE+12000).south.status,'collapsed');
  assert.equal(sampleReplay(SOUTH_COLLAPSE+12000).north.status,'impacted');
  assert.equal(sampleReplay(Date.parse('2001-09-11T10:28:00-04:00')).north.status,'collapsed');
  assert.equal(sampleReplay(Date.parse('2001-09-11T10:28:00-04:00')).north.smoke,0);
});
test('static option skips motion, late dust clears, and rewind restores exact poses', () => {
  assert.equal(sampleReplay(SOUTH_COLLAPSE+3000,false).south.status,'collapsed');
  assert.equal(sampleReplay(SOUTH_COLLAPSE+3000,false).south.smoke,0);
  const pose=sampleReplay(SOUTH_COLLAPSE+4000);
  sampleReplay(SOUTH_COLLAPSE+90000);
  assert.deepEqual(sampleReplay(SOUTH_COLLAPSE+4000),pose);
  assert.equal(sampleReplay(SOUTH_COLLAPSE+301000).south.dust,0);
  assert.equal(sampleReplay(SOUTH_COLLAPSE-1).south.dust,0);
});
test('authored descent and tilt interpolate monotonically with finite bounds', () => {
  let last=sampleSouthPose(0);
  for(let t=.1;t<=12;t+=.1) {
    const pose=sampleSouthPose(t);
    assert.ok(pose.front<=last.front && pose.front>=0);
    assert.ok(pose.drop>=last.drop && pose.drop<=310);
    assert.ok(pose.tilt>=last.tilt && pose.cohesion>=0 && pose.cohesion<=1);
    last=pose;
  }
  assert.deepEqual(sampleSouthPose(100),sampleSouthPose(12));
  assert.deepEqual(sampleSouthPose(-10),sampleSouthPose(0));
});
test('plume samples are reproducible without accumulated particle state', () => {
  const first=smokeParticle(12,240);
  smokeParticle(12,3600);
  assert.deepEqual(smokeParticle(12,240),first);
  assert.ok(first.opacity>=0 && first.opacity<=.16);
  assert.ok(first.radius>=13 && first.radius<=43);
});
