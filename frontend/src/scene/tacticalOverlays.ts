import {
  BufferGeometry,
  Float32BufferAttribute,
  Group,
  Line,
  LineBasicMaterial,
  LineDashedMaterial,
  LineSegments,
} from "three";

export function createTacticalEarthOverlays(): {
  group: Group;
  dispose: () => void;
} {
  const group = new Group();
  const disposables: { dispose: () => void }[] = [];

  // 1. Equatorial Coordinate Ring (z = 0, radius = 1.004)
  const eqSegments = 180;
  const eqPositions = new Float32Array((eqSegments + 1) * 3);
  const eqR = 1.004;
  for (let i = 0; i <= eqSegments; i++) {
    const theta = (i / eqSegments) * Math.PI * 2;
    eqPositions[i * 3] = Math.cos(theta) * eqR;
    eqPositions[i * 3 + 1] = Math.sin(theta) * eqR;
    eqPositions[i * 3 + 2] = 0;
  }
  const eqGeom = new BufferGeometry();
  eqGeom.setAttribute("position", new Float32BufferAttribute(eqPositions, 3));
  const eqMat = new LineBasicMaterial({
    color: 0xff765f, // Anomaly coral
    transparent: true,
    opacity: 0.35,
  });
  const eqLine = new Line(eqGeom, eqMat);
  group.add(eqLine);
  disposables.push(eqGeom, eqMat);

  // Equatorial Cardinal Ticks (every 30 degrees)
  const tickPositions: number[] = [];
  for (let deg = 0; deg < 360; deg += 30) {
    const rad = (deg * Math.PI) / 180;
    const isMajor = deg % 90 === 0;
    const r1 = 1.004;
    const r2 = isMajor ? 1.045 : 1.025;
    tickPositions.push(
      Math.cos(rad) * r1, Math.sin(rad) * r1, 0,
      Math.cos(rad) * r2, Math.sin(rad) * r2, 0,
    );
  }
  const tickGeom = new BufferGeometry();
  tickGeom.setAttribute("position", new Float32BufferAttribute(tickPositions, 3));
  const tickMat = new LineBasicMaterial({
    color: 0xff765f,
    transparent: true,
    opacity: 0.5,
  });
  const tickLines = new LineSegments(tickGeom, tickMat);
  group.add(tickLines);
  disposables.push(tickGeom, tickMat);

  // 2. Polar Reticles (North & South Poles at z = +1 and z = -1)
  const addPolarReticle = (isNorth: boolean) => {
    const zSign = isNorth ? 1 : -1;
    const reticleRings = [
      { r: 0.18, latDeg: 80 },
      { r: 0.34, latDeg: 70 },
    ];

    for (const { latDeg } of reticleRings) {
      const z = Math.sin((latDeg * Math.PI) / 180) * zSign * 1.003;
      const ringRadius = Math.cos((latDeg * Math.PI) / 180) * 1.003;
      const positions = new Float32Array((eqSegments + 1) * 3);
      for (let i = 0; i <= eqSegments; i++) {
        const theta = (i / eqSegments) * Math.PI * 2;
        positions[i * 3] = Math.cos(theta) * ringRadius;
        positions[i * 3 + 1] = Math.sin(theta) * ringRadius;
        positions[i * 3 + 2] = z;
      }
      const geom = new BufferGeometry();
      geom.setAttribute("position", new Float32BufferAttribute(positions, 3));
      const mat = new LineBasicMaterial({
        color: 0x6f9b97, // Ion teal
        transparent: true,
        opacity: 0.4,
      });
      group.add(new Line(geom, mat));
      disposables.push(geom, mat);
    }
  };

  addPolarReticle(true);  // North Pole
  addPolarReticle(false); // South Pole

  // 3. LEO Boundary Shell Ring (altitude ~ 800 km, radius = 1.125)
  const leoPositions = new Float32Array((eqSegments + 1) * 3);
  const leoR = 1.125;
  for (let i = 0; i <= eqSegments; i++) {
    const theta = (i / eqSegments) * Math.PI * 2;
    leoPositions[i * 3] = Math.cos(theta) * leoR;
    leoPositions[i * 3 + 1] = Math.sin(theta) * leoR;
    leoPositions[i * 3 + 2] = 0;
  }
  const leoGeom = new BufferGeometry();
  leoGeom.setAttribute("position", new Float32BufferAttribute(leoPositions, 3));
  const leoMat = new LineDashedMaterial({
    color: 0xe7e9ed, // Starlight
    transparent: true,
    opacity: 0.22,
    dashSize: 0.04,
    gapSize: 0.02,
  });
  const leoLine = new Line(leoGeom, leoMat);
  leoLine.computeLineDistances();
  group.add(leoLine);
  disposables.push(leoGeom, leoMat);

  return {
    group,
    dispose: () => {
      for (const d of disposables) {
        d.dispose();
      }
      group.clear();
    },
  };
}
