import { useEffect, useRef } from "react";

interface Particle {
  x: number;
  y: number;
  radius: number;
  alpha: number;
  baseAlpha: number;
  twinkleSpeed: number;
  twinklePhase: number;
  color: string;
}

export function StartupBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const onResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      initParticles();
    };
    window.addEventListener("resize", onResize);

    // Subtle interactive mouse parallax
    let mouseX = width / 2;
    let mouseY = height / 2;
    let targetX = mouseX;
    let targetY = mouseY;

    const onMouseMove = (e: MouseEvent) => {
      targetX = e.clientX;
      targetY = e.clientY;
    };
    window.addEventListener("mousemove", onMouseMove);

    // Starfield strictly in outer space (never over the planet)
    let particles: Particle[] = [];
    const initParticles = () => {
      const count = Math.min(75, Math.floor((width * height) / 18000));
      particles = [];
      const colors = [
        "rgba(255, 255, 255, ",
        "rgba(147, 197, 253, ",
        "rgba(167, 243, 208, ",
        "rgba(254, 240, 138, ",
      ];
      for (let i = 0; i < count; i++) {
        const baseAlpha = 0.25 + Math.random() * 0.6;
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height * 0.35, // Restricted strictly to top space
          radius: 0.6 + Math.random() * 1.3,
          alpha: baseAlpha,
          baseAlpha,
          twinkleSpeed: 0.015 + Math.random() * 0.03,
          twinklePhase: Math.random() * Math.PI * 2,
          color: colors[Math.floor(Math.random() * colors.length)],
        });
      }
    };
    initParticles();

    // Satellite swarm state
    const satellites = [
      { id: "SAT-01", orbit: 0, progress: 0.32, speed: 0.00030, color: "#60a5fa", size: 3.2 },
      { id: "SAT-02", orbit: 0, progress: 0.58, speed: 0.00030, color: "#93c5fd", size: 2.8 },
      { id: "SAT-03", orbit: 1, progress: 0.24, speed: 0.00026, color: "#34d399", size: 3.0 },
      { id: "SAT-04", orbit: 2, progress: 0.74, speed: 0.00034, color: "#a78bfa", size: 3.0 },
    ];

    let lastTime = performance.now();

    const render = (time: number) => {
      const dt = Math.min(50, time - lastTime);
      lastTime = time;

      // Smooth mouse follow
      mouseX += (targetX - mouseX) * 0.04;
      mouseY += (targetY - mouseY) * 0.04;
      const parallaxX = ((mouseX - width / 2) / width) * 12;
      const parallaxY = ((mouseY - height / 2) / height) * 8;

      ctx.clearRect(0, 0, width, height);

      // Compute exact Earth curve position based on background image cover scaling
      const imgW = 4556;
      const imgH = 3000;
      const imgAspect = imgW / imgH;
      const screenAspect = width / height;

      let scale = 1;
      let offsetX = 0;
      let offsetY = 0;

      if (screenAspect > imgAspect) {
        scale = width / imgW;
        offsetY = (height - imgH * scale) / 2;
      } else {
        scale = height / imgH;
        offsetX = (width - imgW * scale) / 2;
      }

      // Exact mathematical Earth center from high-res 4556x3000 image analysis
      const earthCenterX = offsetX + 528.5 * scale + parallaxX * 0.15;
      const earthCenterY = offsetY + 7125 * scale + parallaxY * 0.15;
      const earthRadius = 6160 * scale;

      // ----------------------------------------------------------------------
      // 1. RENDER STARS ONLY IN DEEP SPACE (STRICT EXCLUSION OVER PLANET)
      // ----------------------------------------------------------------------
      for (const p of particles) {
        const px = p.x + parallaxX * 0.3;
        const py = p.y + parallaxY * 0.3;

        // Mathematical distance check: never draw over planet or atmospheric limb
        const distToEarth = Math.hypot(px - earthCenterX, py - earthCenterY);
        if (distToEarth <= earthRadius + 65 * scale) {
          continue; // Strictly omit star if it falls over Earth!
        }

        p.twinklePhase += p.twinkleSpeed;
        p.alpha = p.baseAlpha + Math.sin(p.twinklePhase) * 0.25;
        ctx.beginPath();
        ctx.arc(px, py, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color}${Math.max(0.1, Math.min(1, p.alpha))})`;
        ctx.fill();
      }

      // ----------------------------------------------------------------------
      // 2. ORBIT DEFINITIONS (Accurately calibrated to the Earth image curve)
      // ----------------------------------------------------------------------

      // Orbit 0: Low Earth Orbit (LEO) skimming right above the blue atmospheric limb
      const leoAltitude = 85 * scale;
      const leoRadius = earthRadius + leoAltitude;

      // Orbit 1: Inclined Walker-Delta constellation plane
      const inc1A = earthRadius + 240 * scale;
      const inc1B = inc1A * 0.44;
      const inc1Angle = -0.24; // radians tilt
      const inc1Cx = earthCenterX + 180 * scale;
      const inc1Cy = earthCenterY - 240 * scale;

      // Orbit 2: Crossing Polar / Synchronous corridor
      const inc2A = earthRadius + 340 * scale;
      const inc2B = inc2A * 0.40;
      const inc2Angle = 0.36; // radians tilt
      const inc2Cx = earthCenterX - 140 * scale;
      const inc2Cy = earthCenterY - 300 * scale;

      // Draw Orbit 0 (LEO Circular Arc across the Earth limb)
      ctx.save();
      ctx.beginPath();
      ctx.arc(earthCenterX, earthCenterY, leoRadius, Math.PI * 1.42, Math.PI * 1.76);
      ctx.strokeStyle = "rgba(100, 160, 240, 0.45)";
      ctx.lineWidth = 1.6;
      ctx.shadowColor = "rgba(96, 165, 250, 0.7)";
      ctx.shadowBlur = 10;
      ctx.stroke();

      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(100, 160, 240, 0.12)";
      ctx.stroke();
      ctx.restore();

      // Draw Orbit 1 (Inclined ellipse)
      ctx.save();
      ctx.translate(inc1Cx, inc1Cy);
      ctx.rotate(inc1Angle);
      ctx.beginPath();
      ctx.ellipse(0, 0, inc1A, inc1B, 0, Math.PI * 1.34, Math.PI * 1.96);
      ctx.strokeStyle = "rgba(52, 211, 153, 0.35)";
      ctx.lineWidth = 1.4;
      ctx.setLineDash([5, 6]);
      ctx.stroke();
      ctx.restore();

      // Draw Orbit 2 (Counter-inclined ellipse)
      ctx.save();
      ctx.translate(inc2Cx, inc2Cy);
      ctx.rotate(inc2Angle);
      ctx.beginPath();
      ctx.ellipse(0, 0, inc2A, inc2B, 0, Math.PI * 1.24, Math.PI * 1.86);
      ctx.strokeStyle = "rgba(167, 139, 250, 0.35)";
      ctx.lineWidth = 1.4;
      ctx.setLineDash([4, 7]);
      ctx.stroke();
      ctx.restore();

      // Calculate satellite positions
      const satPositions: { x: number; y: number; sat: typeof satellites[0] }[] = [];

      for (const sat of satellites) {
        sat.progress = (sat.progress + sat.speed * (dt / 16.6)) % 1;

        let x = 0;
        let y = 0;

        if (sat.orbit === 0) {
          const angle = Math.PI * (1.44 + sat.progress * 0.30);
          x = earthCenterX + Math.cos(angle) * leoRadius;
          y = earthCenterY + Math.sin(angle) * leoRadius;
        } else if (sat.orbit === 1) {
          const angle = Math.PI * (1.36 + sat.progress * 0.58);
          const ux = Math.cos(angle) * inc1A;
          const uy = Math.sin(angle) * inc1B;
          x = inc1Cx + ux * Math.cos(inc1Angle) - uy * Math.sin(inc1Angle);
          y = inc1Cy + ux * Math.sin(inc1Angle) + uy * Math.cos(inc1Angle);
        } else {
          const angle = Math.PI * (1.26 + sat.progress * 0.56);
          const ux = Math.cos(angle) * inc2A;
          const uy = Math.sin(angle) * inc2B;
          x = inc2Cx + ux * Math.cos(inc2Angle) - uy * Math.sin(inc2Angle);
          y = inc2Cy + ux * Math.sin(inc2Angle) + uy * Math.cos(inc2Angle);
        }

        satPositions.push({ x, y, sat });
      }

      // Draw inter-satellite telemetry beams (when within distance)
      for (let i = 0; i < satPositions.length; i++) {
        for (let j = i + 1; j < satPositions.length; j++) {
          const p1 = satPositions[i];
          const p2 = satPositions[j];
          const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
          if (dist < width * 0.42) {
            const beamAlpha = (1 - dist / (width * 0.42)) * 0.24;
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = `rgba(147, 197, 253, ${beamAlpha})`;
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 5]);
            ctx.stroke();
            ctx.setLineDash([]);
          }
        }
      }

      // Draw satellite nodes
      for (const { x, y, sat } of satPositions) {
        const pulse = 1 + Math.sin(time * 0.004 + sat.progress * 10) * 0.25;
        const haloGrad = ctx.createRadialGradient(x, y, 0, x, y, sat.size * 6 * pulse);
        haloGrad.addColorStop(0, sat.color + "cc");
        haloGrad.addColorStop(0.35, sat.color + "44");
        haloGrad.addColorStop(1, "transparent");

        ctx.fillStyle = haloGrad;
        ctx.beginPath();
        ctx.arc(x, y, sat.size * 6 * pulse, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(x, y, sat.size, 0, Math.PI * 2);
        ctx.fill();

        ctx.font = "10px 'Chakra Petch', monospace";
        ctx.fillStyle = "rgba(220, 235, 255, 0.85)";
        ctx.fillText(sat.id, x + 8, y - 6);
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mousemove", onMouseMove);
    };
  }, []);

  return (
    <div className="startup-bg-container" aria-hidden="true">
      {/* 4K Ultra-Sharp Earth Orbit Background Image */}
      <div className="startup-bg-image" />
      {/* Calibrated Satellite Orbits & Telemetry Canvas (Stars strictly in space) */}
      <canvas ref={canvasRef} className="startup-bg-canvas" />
      {/* Atmospheric Space Vignette */}
      <div className="startup-bg-vignette" />
    </div>
  );
}
