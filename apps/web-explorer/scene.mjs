// NIST event times; geographic centers from OSM memorial-pool reference geometry.
// Geometry and atmospheric effects are illustrative, not a forensic simulation.
export const TOWER_BEARING = -29.117;
export const TOWERS = [
  { id: 'north', name: 'North Tower', lng: -74.0131756, lat: 40.7121392, height: 417,
    impact: '2001-09-11T08:46:30-04:00', collapse: '2001-09-11T10:28:22-04:00',
    face: 1, impactBase: 350, impactTop: 377 },
  { id: 'south', name: 'South Tower', lng: -74.0130805, lat: 40.7110296, height: 415,
    impact: '2001-09-11T09:02:59-04:00', collapse: '2001-09-11T09:58:59-04:00',
    face: -1, impactBase: 290, impactTop: 324 },
];

export function getSceneState(historicalTime) {
  const time = historicalTime instanceof Date ? historicalTime.getTime()
    : typeof historicalTime === 'number' ? historicalTime : Date.parse(historicalTime);
  if (!Number.isFinite(time)) throw new TypeError('A valid historical time is required');
  return Object.fromEntries(TOWERS.map(tower => [tower.id,
    time >= Date.parse(tower.collapse) ? 'collapsed'
      : time >= Date.parse(tower.impact) ? 'impacted' : 'intact',
  ]));
}

// Local x/y axes follow the existing rotated tower footprints; +y is north face.
function coordinate(tower, x, y) {
  const angle = TOWER_BEARING * Math.PI / 180;
  return [
    tower.lng + (x * Math.cos(angle) - y * Math.sin(angle)) / (111320 * Math.cos(tower.lat * Math.PI / 180)),
    tower.lat + (x * Math.sin(angle) + y * Math.cos(angle)) / 111320,
  ];
}

function polygon(tower, points, properties) {
  return { type: 'Feature', properties: { tower: tower.id, ...properties },
    geometry: { type: 'Polygon', coordinates: [[...points, points[0]].map(([x, y]) => coordinate(tower, x, y))] } };
}

function box(tower, x, y, width, depth, properties) {
  return polygon(tower, [[x-width/2,y-depth/2], [x+width/2,y-depth/2],
    [x+width/2,y+depth/2], [x-width/2,y+depth/2]], properties);
}

function cloud(tower, x, y, radius, base, height, kind) {
  return polygon(tower, Array.from({ length: 16 }, (_, i) => {
    const angle = i * Math.PI / 8;
    return [x + Math.cos(angle) * radius, y + Math.sin(angle) * radius * .8];
  }), { kind, base, height });
}

export function buildScene(scene) {
  const solid = [], smoke = [], dust = [], labels = [];
  for (const tower of TOWERS) {
    const status = scene[tower.id];
    labels.push({ type: 'Feature', properties: {
      label: `${tower.name.toUpperCase()} · ${status.toUpperCase()}`,
    }, geometry: { type: 'Point', coordinates: [tower.lng, tower.lat] } });
    if (status === 'collapsed') {
      solid.push(box(tower, 0, 0, 76, 76, { kind: 'debris', base: 0, height: 7 }));
      for (let i = 0; i < 5; i++) {
        solid.push(box(tower, (i % 3 - 1) * 19, (Math.floor(i / 3) - .5) * 25,
          21, 23, { kind: 'debris', base: 0, height: 10 + (i % 3) * 4 }));
      }
      dust.push(cloud(tower, 0, 0, 76, 0, 23, 'dust'),
        cloud(tower, 22, -24, 52, 14, 39, 'dust'));
      continue;
    }
    solid.push(box(tower, 0, 0, 63.4, 63.4, { kind: 'tower', base: 0, height: tower.height }));
    if (tower.id === 'north') solid.push(box(tower, 0, 0, 5.2, 5.2,
      { kind: 'antenna', base: 417, height: 527 }));
    if (status === 'impacted') {
      // Thin exterior patches, not a band around all four sides. South is offset east.
      for (let i = 0; i < 5; i++) {
        solid.push(box(tower, (i - 2) * 9 + (tower.id === 'south' ? 7 : 0),
          tower.face * 32, 9.5, 2.5, { kind: 'damage',
            base: tower.impactBase + Math.abs(i - 2) * 3,
            height: tower.impactTop - Math.abs(i - 2) * 2 }));
      }
      // Static translucent volumes anchored at impact height; no clock or animation.
      for (let i = 0; i < 5; i++) smoke.push(cloud(tower,
        7 + i * 9, tower.face * 35 - i * 9, 15 + i * 5,
        tower.impactTop - 12 + i * 32, tower.impactTop + 30 + i * 32, 'smoke'));
    }
  }
  const collection = features => ({ type: 'FeatureCollection', features });
  return { solid: collection(solid), smoke: collection(smoke), dust: collection(dust), labels: collection(labels) };
}

export const SCENE_LAYERS = ['historical-wtc-3d', 'historical-wtc-labels', 'wtc-smoke', 'wtc-dust'];

export function updateSceneSources(map, scene) {
  const data = buildScene(scene);
  for (const [source, key] of [['historical-wtc', 'solid'], ['wtc-labels', 'labels'],
    ['wtc-smoke', 'smoke'], ['wtc-dust', 'dust']]) map.getSource(source).setData(data[key]);
}
