import { TOWERS } from './scene.mjs';

export const SOUTH_COLLAPSE = Date.parse(TOWERS[1].collapse);
export const COLLAPSE_DURATION = 12;
// Authored illustrative poses, NOT a structural solver or measured trajectory.
// seconds, descending front (m), upper-section drop (m), tilt (degrees), cohesion
export const SOUTH_POSES = [
  [0, 300, 0, 0, 1], [2, 295, 8, 6, 1], [4, 235, 45, 14, .85],
  [8, 85, 200, 20, .35], [12, 0, 310, 22, 0],
];
const clamp = (x, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));

export function sampleSouthPose(seconds) {
  const t = clamp(seconds, 0, COLLAPSE_DURATION);
  const next = SOUTH_POSES.findIndex(row => row[0] >= t);
  const b = SOUTH_POSES[Math.max(1, next)], a = SOUTH_POSES[Math.max(1, next) - 1];
  const f = (t - a[0]) / (b[0] - a[0]);
  const values = a.map((value, i) => value + (b[i] - value) * f);
  return { front: values[1], drop: values[2], tilt: values[3] * Math.PI / 180,
    cohesion: values[4] };
}

export function sampleReplay(historicalTime, motion = true) {
  const time = Number(historicalTime);
  if (!Number.isFinite(time)) throw new TypeError('A valid historical time is required');
  return Object.fromEntries(TOWERS.map(tower => {
    const impactAge = (time - Date.parse(tower.impact)) / 1000;
    const collapseAge = (time - Date.parse(tower.collapse)) / 1000;
    const collapsing = motion && tower.id === 'south' && collapseAge >= 0 && collapseAge < COLLAPSE_DURATION;
    return [tower.id, {
      status: collapsing ? 'collapsing' : collapseAge >= 0 ? 'collapsed' : impactAge >= 0 ? 'impacted' : 'intact',
      impactAge, collapseAge,
      pose: sampleSouthPose(collapsing ? collapseAge : collapseAge >= 0 ? COLLAPSE_DURATION : 0),
      // Dust thins over five minutes; residue remains in the geometry, not the air.
      dust: collapseAge < 0 ? 0 : motion ? clamp(collapseAge / 5) * clamp(1 - collapseAge / 300) : .25,
      smoke: impactAge < 0 || collapseAge >= COLLAPSE_DURATION || (collapseAge >= 0 && (!motion || tower.id === 'north')) ? 0
        : clamp(impactAge / 80, .15, 1) * (collapseAge < 0 ? 1 : 1 - collapseAge / COLLAPSE_DURATION),
      effectTime: motion ? Math.max(0, impactAge) : 120,
    }];
  }));
}

// Fixed spatial variation: every seek to a given time reconstructs identical effects.
export function seeded(index) {
  const value = Math.sin(index * 127.1 + 311.7) * 43758.5453;
  return value - Math.floor(value);
}

export function smokeParticle(index, age) {
  const life = 70;
  const elapsed = (age + seeded(index) * life) % life;
  const phase = elapsed / life;
  return { x: 8 + phase * 115 + (seeded(index + 1) - .5) * 30,
    y: -phase * 75 + (seeded(index + 2) - .5) * 35,
    z: phase * 180, radius: 13 + phase * 30,
    opacity: Math.sin(phase * Math.PI) * .16 };
}
