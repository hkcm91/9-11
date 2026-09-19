import { TOWERS, TOWER_BEARING } from './scene.mjs';

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

// Preserve physical size; breakup separates full-size model sections.
export function upperSectionPose(index, bottom, split, collapseAge, cohesion) {
  const separation = Math.max(0, 1 - cohesion);
  const age = Math.max(0, collapseAge - 3);
  return { x: (seeded(index + 600) - .5) * separation * 35,
    y: (seeded(index + 620) - .5) * separation * 28,
    z: bottom - split - separation * age * index * 1.8,
    angle: (seeded(index + 640) - .5) * separation * .35 };
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
    opacity: (.35 + .65 * Math.sin(phase * Math.PI)) * .24 * Math.min(1, (1-phase)*8) };
}

// NIST NCSTAR 1, Table 6-4 central estimates. Only a short, straight final
// approach is extrapolated; this is not a reconstruction of the entire flight.
export const AIRCRAFT_APPROACH = {
  north: { heading: 180.3, descent: 10.6, bank: 25, speed: 443 * .44704, offset: 0 },
  south: { heading: 13, descent: 6, bank: 38, speed: 542 * .44704, offset: 7 },
};
export function sampleAircraft(tower, historicalTime, motion = true) {
  const age = (Number(historicalTime) - Date.parse(tower.impact)) / 1000;
  if (!Number.isFinite(age)) throw new TypeError('A valid historical time is required');
  const approach = AIRCRAFT_APPROACH[tower.id];
  const heading = approach.heading * Math.PI / 180, descent = approach.descent * Math.PI / 180;
  const travel = age * approach.speed;
  return { visible: age >= -12 && age < 0, age,
    x: approach.offset + Math.sin(heading) * Math.cos(descent) * travel,
    y: tower.face * 32.1 + Math.cos(heading) * Math.cos(descent) * travel,
    z: (tower.impactBase + tower.impactTop) / 2 - Math.sin(descent) * travel,
    heading, descent, bank: approach.bank * Math.PI / 180,
    // Subdued, finite impact cue; no flashes, sound, or repeating explosion.
    impact: motion && age >= 0 && age < 6 ? (1 - age / 6) : 0,
    radius: 9 + Math.min(6, Math.max(0, age)) * 5,
  };
}

// Symbolic local fire, not a model of measured fire spread or temperature.
// Slow variation follows only the historical cursor; static mode freezes it.
export function sampleFlame(tower, historicalTime, index, motion = true) {
  const age = (Number(historicalTime) - Date.parse(tower.impact)) / 1000;
  if (!Number.isFinite(age)) throw new TypeError('A valid historical time is required');
  const phase = (motion ? Math.max(0, age) * .9 : 0) + index * 2.4;
  const variation = .85 + .15 * Math.sin(phase);
  return { visible: age >= 0 && Number(historicalTime) < Date.parse(tower.collapse),
    x: (index - 4) * 5.2 + (tower.id === 'south' ? 7 : 0),
    y: tower.face * 33.8,
    base: tower.impactBase + 3 + seeded(index + 800) * 6,
    width: 3.5 + seeded(index + 810) * 3,
    height: (8 + seeded(index + 820) * 10) * variation,
    opacity: .7 + .1 * Math.sin(phase + 1),
  };
}


// The ground projection and 3D guide use the same sampled approach as the plane.
// These samples are estimates, NOT recorded radar returns.
export function approachTrack(tower) {
  return Array.from({length:25},(_,i)=>sampleAircraft(tower,Date.parse(tower.impact)-12000+i*500));
}
export function aircraftCoordinate(tower, position) {
  const angle=TOWER_BEARING*Math.PI/180;
  return [tower.lng+(position.x*Math.cos(angle)-position.y*Math.sin(angle))/(111320*Math.cos(tower.lat*Math.PI/180)),
    tower.lat+(position.x*Math.sin(angle)+position.y*Math.cos(angle))/111320];
}
export function aircraftMapData(time) {
  const features=[];
  for(const tower of TOWERS) {
    const flight=sampleAircraft(tower,time);
    // Guides are reference geometry; only aircraft positions depend on the active window.
    const name=tower.id==='north'?'Flight 11':'Flight 175';
    features.push({type:'Feature',properties:{kind:'route',tower:tower.id,label:name+' · estimated ground track'},
      geometry:{type:'LineString',coordinates:approachTrack(tower).map(p=>aircraftCoordinate(tower,p))}});
    if(flight.visible) features.push({type:'Feature',properties:{kind:'aircraft',tower:tower.id,
      label:name+' · ground position',heading:(AIRCRAFT_APPROACH[tower.id].heading-TOWER_BEARING+360)%360},
      geometry:{type:'Point',coordinates:aircraftCoordinate(tower,flight)}});
  }
  return {type:'FeatureCollection',features};
}
