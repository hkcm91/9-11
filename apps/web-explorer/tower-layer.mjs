import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js';
import { TOWERS, TOWER_BEARING } from './scene.mjs';
import { sampleReplay, seeded, smokeParticle, upperSectionPose } from './replay.mjs';

// Meter-based procedural models. All geometry is authored locally, Z is up.
export function createTowerLayer(maplibregl) {
  const scene = new THREE.Scene();
  const camera = new THREE.Camera();
  const root = new THREE.Group();
  scene.add(root);
  scene.add(new THREE.AmbientLight(0xdbe2e7, 2));
  const light = new THREE.DirectionalLight(0xfff1d5, 2.1);
  light.position.set(-300, -200, 800); scene.add(light);
  const box = new THREE.BoxGeometry(1, 1, 1);
  const outline = new THREE.Shape();
  const c = 2.1 / 63.4;
  const corners = [[-.5+c,-.5],[.5-c,-.5],[.5,-.5+c],[.5,.5-c],[.5-c,.5],[-.5+c,.5],[-.5,.5-c],[-.5,-.5+c]];
  corners.forEach(([x,y],i)=>i ? outline.lineTo(x,y) : outline.moveTo(x,y)); outline.closePath();
  const towerBody = new THREE.ExtrudeGeometry(outline,{depth:1,bevelEnabled:false});
  towerBody.translate(0,0,-.5);
  // Soft camera-facing density patches avoid visibly spherical smoke bubbles.
  const cloudGeometry = new THREE.PlaneGeometry(2, 2);
  const canvas = document.createElement('canvas'); canvas.width=128; canvas.height=128;
  const context=canvas.getContext('2d');
  const gradient=context.createRadialGradient(64,64,0,64,64,64);
  gradient.addColorStop(0,'rgba(255,255,255,0.85)');
  gradient.addColorStop(.35,'rgba(255,255,255,0.65)');
  gradient.addColorStop(.7,'rgba(255,255,255,0.2)');
  gradient.addColorStop(1,'rgba(255,255,255,0)');
  context.fillStyle=gradient;context.fillRect(0,0,128,128);
  const cloudTexture=new THREE.CanvasTexture(canvas);
  const faceCamera=new THREE.Quaternion(), pitchRotation=new THREE.Quaternion();
  const axisZ=new THREE.Vector3(0,0,1),axisX=new THREE.Vector3(1,0,0);
  const materials = {
    wall: new THREE.MeshLambertMaterial({ color: 0x737977 }),
    frame: new THREE.MeshLambertMaterial({ color: 0xb7b9b3 }),
    roof: new THREE.MeshLambertMaterial({ color: 0x8a8980 }),
    damage: new THREE.MeshLambertMaterial({ color: 0x242120 }),
    rubble: new THREE.MeshLambertMaterial({ color: 0x827b70 }),
    plaza: new THREE.MeshLambertMaterial({ color: 0x66665e }),
  };
  const mesh = (parent, material, x, y, z, w, d, h) => {
    const node = new THREE.Mesh(box, material);
    node.position.set(x, y, z); node.scale.set(w, d, h); parent.add(node); return node;
  };
  const instances = (parent, material, entries) => {
    const result = new THREE.InstancedMesh(box, material, entries.length);
    const dummy = new THREE.Object3D();
    entries.forEach(([x,y,z,w,d,h], index) => {
      dummy.position.set(x,y,z); dummy.scale.set(w,d,h); dummy.updateMatrix();
      result.setMatrixAt(index, dummy.matrix);
    });
    // Camera projection includes model transform; explicit bounds avoid incorrect culling.
    result.frustumCulled = false; parent.add(result); return result;
  };
  const origin = maplibregl.MercatorCoordinate.fromLngLat([TOWERS[0].lng, TOWERS[0].lat], 0);
  const scale = origin.meterInMercatorCoordinateUnits();
  const transform = new THREE.Matrix4().makeTranslation(origin.x, origin.y, origin.z)
    .scale(new THREE.Vector3(scale, -scale, scale));

  const models = TOWERS.map(tower => {
    const group = new THREE.Group();
    const location = maplibregl.MercatorCoordinate.fromLngLat([tower.lng,tower.lat],0);
    group.position.set((location.x-origin.x)/scale, -(location.y-origin.y)/scale, 0);
    group.rotation.z = TOWER_BEARING * Math.PI / 180;
    root.add(group);
    const lower = new THREE.Group(), upper = new THREE.Group();
    const split = tower.id === 'south' ? 300 : 350;
    upper.position.z = split; group.add(lower, upper);
    const sections = [];
    const section = (parent, bottom, top, offset) => {
      const part = new THREE.Group(); part.position.z = bottom-offset; parent.add(part);
      const height = top-bottom;
      const shell = mesh(part, materials.wall,0,0,height/2,63.4,63.4,height);
      shell.geometry = towerBody;
      const ribs = [];
      for(let i=0;i<59;i++) {
        const x=(i-29)*1.016;
        ribs.push([x,-31.65,height/2,.36,.55,height],[x,31.65,height/2,.36,.55,height],
          [-31.65,x,height/2,.55,.36,height],[31.65,x,height/2,.55,.36,height]);
      }
      for(let floor=Math.ceil((bottom+.1)/(tower.height/110));floor*(tower.height/110)<top;floor++) {
        const z=floor*(tower.height/110)-bottom;
        ribs.push([0,-31.65,z,59,.5,.24],
        [0,31.65,z,59,.5,.24],[-31.65,0,z,.5,59,.24],[31.65,0,z,.5,59,.24]);
      }
      instances(part,materials.frame,ribs); sections.push({part,bottom,top,parent});
    };
    for(let bottom=0;bottom<split;bottom+=19) section(lower,bottom,Math.min(split,bottom+19),0);
    for(let bottom=split;bottom<tower.height;bottom+=38) section(upper,bottom,Math.min(tower.height,bottom+38),split);
    // Mechanical bands, parapet and rooftop equipment distinguish the silhouettes.
    for(const floor of [7,41,75,108]) {
      const z=floor*tower.height/110;
      const section = sections.find(s => z >= s.bottom && z < s.top);
      const parent = section.part, local=z-section.bottom;
      mesh(parent,materials.roof,0,0,local,63.7,63.7,2*tower.height/110);
    }
    const roofSection = sections.at(-1);
    const roof = roofSection.part, roofBase = roofSection.bottom;
    mesh(roof,materials.roof,0,0,tower.height-roofBase,63.5,63.5,2);
    mesh(roof,materials.frame,0,0,tower.height-roofBase+1.5,64,64,1);
    mesh(roof,materials.roof,0,0,tower.height-roofBase+3,18,24,5);
    if(tower.id==='north') {
      mesh(roof,materials.frame,0,0,417-roofBase+55,2.4,2.4,110);
      mesh(roof,materials.roof,0,0,417-roofBase+7,7,7,14);
    }
    const damage = new THREE.Group(); group.add(damage);
    for(let i=0;i<9;i++) {
      const x=(i-4)*5.4+(tower.id==='south'?7:0), h=(tower.impactTop-tower.impactBase)*(1-.11*Math.abs(i-4));
      mesh(damage,materials.damage,x,tower.face*32.1,(tower.impactTop+tower.impactBase)/2+(seeded(i)-.5)*5,5.6,1.2,h);
    }
    const debris = new THREE.Group(); group.add(debris);
    for(let i=0;i<45;i++) {
      const node=mesh(debris,materials.rubble,(seeded(i+40)-.5)*78,(seeded(i+90)-.5)*78,
        2+seeded(i+20)*7,5+seeded(i)*15,4+seeded(i+10)*12,3+seeded(i+30)*12);
      node.rotation.set(seeded(i)*.5,seeded(i+2)*.4,seeded(i+3)*Math.PI);
    }
    const fragments = new THREE.Group(); group.add(fragments);
    for(let i=0;i<20;i++) mesh(fragments,materials.frame,0,0,0,5,1,12);
    const clouds = (count,color) => Array.from({length:count},()=>{
      const material=new THREE.MeshBasicMaterial({color,map:cloudTexture,transparent:true,opacity:0,depthWrite:false,side:THREE.DoubleSide});
      const node=new THREE.Mesh(cloudGeometry,material); node.frustumCulled=false; group.add(node); return node;
    });
    return {tower,group,lower,upper,split,sections,damage,debris,fragments,
      smoke:clouds(28,0x64635e),dust:clouds(24,0xb1a798)};
  });
  // Low, neutral plaza surface only; surrounding building geometry stays on the map.
  mesh(root,materials.plaza,35,-55,-1,160,205,1);

  let renderer, map, lastTime=0, visible=true, motion=true;
  const layer = {
    id:'wtc-detailed',type:'custom',renderingMode:'3d',
    onAdd(instance,gl) {
      map=instance;
      renderer=new THREE.WebGLRenderer({canvas:map.getCanvas(),context:gl,antialias:true});
      renderer.autoClear=false;
    },
    setTime(time, options={}) {
      lastTime=Number(time); motion=options.motion ?? motion; visible=options.visible ?? visible;
      root.visible=visible;
      const states=sampleReplay(lastTime,motion);
      for(const model of models) {
        const s=states[model.tower.id], collapsing=s.status==='collapsing', standing=s.status==='intact'||s.status==='impacted';
        model.lower.visible=standing||collapsing; model.upper.visible=standing||(collapsing&&s.pose.cohesion>.05);
        model.upper.position.set(collapsing?s.pose.drop*.08:0,collapsing?-s.pose.drop*.04:0,model.split-(collapsing?s.pose.drop:0));
        model.upper.rotation.set(collapsing?s.pose.tilt*.6:0,collapsing?s.pose.tilt:0,0);
        model.upper.scale.setScalar(1);
        model.sections.filter(section=>section.parent===model.upper).forEach(({part,bottom},index)=>{
          const pose=upperSectionPose(index,bottom,model.split,collapsing?s.collapseAge:0,collapsing?s.pose.cohesion:1);
          part.position.set(pose.x,pose.y,pose.z);part.rotation.set(pose.angle,-pose.angle*.5,0);
        });
        model.sections.forEach(({part,bottom,parent})=>{part.visible=parent===model.upper||!collapsing||bottom<s.pose.front;});
        // Hide lower mechanical bands as the descending front passes them.
        model.lower.children.filter(node=>node.isMesh).forEach(node=>{node.visible=!collapsing||node.position.z<s.pose.front;});
        model.damage.visible=s.status==='impacted';
        model.debris.visible=s.status==='collapsed'||(collapsing&&s.collapseAge>5);
        model.debris.scale.z=collapsing?Math.min(1,(s.collapseAge-5)/7):1;
        model.fragments.visible=collapsing&&s.collapseAge>2;
        model.fragments.children.forEach((node,i)=>{
          const t=Math.max(0,s.collapseAge-2),a=seeded(i+200)*Math.PI*2;
          node.position.set(Math.cos(a)*(32+t*(3+seeded(i)*5)),Math.sin(a)*(32+t*(3+seeded(i+1)*5)),
            Math.max(4,model.split+seeded(i+2)*60-t*t*4));
          node.rotation.set(t*.13+seeded(i),t*.2, a);
        });
        model.smoke.forEach((node,i)=>{
          const p=smokeParticle(i,s.effectTime);
          node.visible=s.smoke>0;
          node.position.set(p.x,model.tower.face*34+p.y,model.tower.impactTop+p.z);
          node.scale.set(p.radius,p.radius*.85,p.radius*1.1);
          node.material.opacity=p.opacity*s.smoke*1.6;
        });
        model.dust.forEach((node,i)=>{
          const age=motion?Math.max(0,s.collapseAge):20,a=seeded(i+300)*Math.PI*2;
          const spread=Math.min(150,15+age*3)*( .3+seeded(i+90)*.7);
          node.visible=s.dust>0;
          node.position.set(Math.cos(a)*spread,Math.sin(a)*spread,12+seeded(i+20)*30);
          const radius=18+Math.min(35,age*1.3)+seeded(i)*12;
          node.scale.set(radius,radius, radius*.65);node.material.opacity=s.dust*.12;
        });
      }
      map?.triggerRepaint();
    },
    render(gl,args) {
      if(!visible) return;
      faceCamera.setFromAxisAngle(axisZ,(-map.getBearing()-TOWER_BEARING)*Math.PI/180);
      pitchRotation.setFromAxisAngle(axisX,map.getPitch()*Math.PI/180);
      faceCamera.multiply(pitchRotation);
      for(const model of models) for(const node of [...model.smoke,...model.dust]) node.quaternion.copy(faceCamera);
      camera.projectionMatrix.fromArray(args.defaultProjectionData.mainMatrix).multiply(transform);
      camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
      renderer.resetState(); renderer.render(scene,camera); renderer.resetState();
    },
    onRemove() {
      const geometries=new Set(),mats=new Set();
      scene.traverse(node=>{if(node.geometry)geometries.add(node.geometry);if(node.material)mats.add(node.material);});
      geometries.forEach(g=>g.dispose());mats.forEach(m=>m.dispose());cloudTexture.dispose();renderer?.dispose();
    },
  };
  return layer;
}
