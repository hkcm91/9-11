export function timeBounds(item) {
  const parse = value => value ? Date.parse(value) : NaN;
  const start = parse(item.time?.start_time), end = parse(item.time?.end_time);
  if (!Number.isFinite(start) && !Number.isFinite(end)) return null;
  return { start: Number.isFinite(start) ? start : end, end: Number.isFinite(end) ? end : start };
}

export function matchesHistoricalTime(item, current, windowMinutes, includeUntimed = false) {
  const bounds = timeBounds(item);
  if (!bounds) return includeUntimed && Boolean(item.location);
  const radius = windowMinutes * 60000;
  return bounds.start <= Number(current) + radius && bounds.end >= Number(current) - radius;
}

export function summarizeTimes(items) {
  const timed = items.filter(item => timeBounds(item)).length;
  return { timed, untimed: items.length - timed };
}
