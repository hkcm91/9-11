import test from 'node:test';
import assert from 'node:assert/strict';
import { matchesHistoricalTime, summarizeTimes } from './evidence-time.mjs';

const at = time => new Date(`2001-09-11T${time}:00-04:00`);
test('untimed photos are opt-in and are counted separately', () => {
  const photo = { time: null, location: { latitude: 40.7 } };
  assert.equal(matchesHistoricalTime(photo, at('10:39'), 5), false);
  assert.equal(matchesHistoricalTime(photo, at('10:39'), 5, true), true);
  assert.equal(matchesHistoricalTime({time:null}, at('10:39'), 5, true), false);
  assert.deepEqual(summarizeTimes([photo, {time: {start_time: at('10:39').toISOString()}}]), {timed:1,untimed:1});
});
test('single-ended timestamps are instants, not unbounded time ranges', () => {
  for (const key of ['start_time', 'end_time']) {
    const photo = { time: { [key]: at('08:46').toISOString() } };
    assert.equal(matchesHistoricalTime(photo, at('10:39'), 5), false);
    assert.equal(matchesHistoricalTime(photo, at('08:40'), 5), false);
    assert.equal(matchesHistoricalTime(photo, at('08:41'), 5), true);
  }
});
test('real intervals intersect the window; invalid timestamps are untimed', () => {
  const photo = { time: {start_time: at('09:00').toISOString(), end_time:at('09:30').toISOString()} };
  assert.equal(matchesHistoricalTime(photo, at('09:20'), 5), true);
  assert.equal(matchesHistoricalTime(photo, at('10:39'), 5), false);
  assert.equal(matchesHistoricalTime({time:{start_time:'invalid'}}, at('10:39'), 5), false);
});
