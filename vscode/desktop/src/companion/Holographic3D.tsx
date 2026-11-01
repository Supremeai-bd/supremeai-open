import { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface Holographic3DProps {
  state?: 'idle' | 'listening' | 'thinking' | 'speaking';
  className?: string;
}

export default function Holographic3D({ state = 'idle', className = '' }: Holographic3DProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let width = container.clientWidth || 500;
    let height = container.clientHeight || 600;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0, 7.5);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // 2. Volumetric 3D Holographic Entity Group
    const holoEntity = new THREE.Group();
    scene.add(holoEntity);

    // Cyan phosphor core glow material
    const holoMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x00f0ff,
      emissive: 0x00f0ff,
      emissiveIntensity: 0.6,
      roughness: 0.2,
      metalness: 0.1,
      transmission: 0.7, // Holographic translucent glass
      opacity: 0.85,
      transparent: true,
      wireframe: false,
    });

    const wireframeMat = new THREE.MeshBasicMaterial({
      color: 0x80f5ff,
      wireframe: true,
      transparent: true,
      opacity: 0.35,
    });

    // Torso / Neck / Head Hierarchy for realistic anatomical kinesics
    const torsoGeo = new THREE.CylinderGeometry(0.7, 0.9, 1.8, 24);
    const torsoMesh = new THREE.Mesh(torsoGeo, holoMaterial);
    torsoMesh.position.y = -1.2;
    holoEntity.add(torsoMesh);

    const neckGeo = new THREE.CylinderGeometry(0.28, 0.32, 0.6, 16);
    const neckMesh = new THREE.Mesh(neckGeo, holoMaterial);
    neckMesh.position.y = 0.05;
    holoEntity.add(neckMesh);

    const headGroup = new THREE.Group();
    headGroup.position.y = 0.8;
    holoEntity.add(headGroup);

    // Stylized Anime Head geometry
    const headGeo = new THREE.SphereGeometry(0.85, 32, 32);
    headGeo.scale(1.0, 1.15, 1.05);
    const headMesh = new THREE.Mesh(headGeo, holoMaterial);
    headGroup.add(headMesh);

    const headWire = new THREE.Mesh(headGeo, wireframeMat);
    headWire.scale.set(1.02, 1.02, 1.02);
    headGroup.add(headWire);

    // Expressive Eyes with Pupils
    const eyeGeo = new THREE.SphereGeometry(0.14, 16, 16);
    const pupilMat = new THREE.MeshBasicMaterial({ color: 0x00ffff });

    const leftEye = new THREE.Mesh(eyeGeo, pupilMat);
    leftEye.position.set(-0.32, 0.1, 0.75);
    leftEye.scale.set(1, 1.3, 0.5);
    headGroup.add(leftEye);

    const rightEye = new THREE.Mesh(eyeGeo, pupilMat);
    rightEye.position.set(0.32, 0.1, 0.75);
    rightEye.scale.set(1, 1.3, 0.5);
    headGroup.add(rightEye);

    // Luminous Holographic Hair Strands (layered volume)
    const hairGroup = new THREE.Group();
    const hairMat = new THREE.MeshPhysicalMaterial({
      color: 0xe0f7ff,
      emissive: 0x00e1ff,
      emissiveIntensity: 0.4,
      transparent: true,
      opacity: 0.75,
      roughness: 0.3,
    });

    for (let i = -4; i <= 4; i++) {
      const strandGeo = new THREE.ConeGeometry(0.2, 1.4, 8);
      const strand = new THREE.Mesh(strandGeo, hairMat);
      strand.position.set(i * 0.22, 0.55 - Math.abs(i) * 0.08, 0.5 - Math.abs(i) * 0.05);
      strand.rotation.z = -i * 0.12;
      strand.rotation.x = 0.2;
      hairGroup.add(strand);
    }
    headGroup.add(hairGroup);

    // 3. Holographic Projection Floor Rings (Volumetric Emitter)
    const ringsGroup = new THREE.Group();
    ringsGroup.position.y = -2.3;
    scene.add(ringsGroup);

    const ringMat1 = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.6,
      wireframe: true,
    });
    const ring1 = new THREE.Mesh(new THREE.RingGeometry(1.4, 1.48, 48), ringMat1);
    ring1.rotation.x = Math.PI / 2;
    ringsGroup.add(ring1);

    const ring2 = new THREE.Mesh(new THREE.RingGeometry(2.1, 2.18, 64), ringMat1);
    ring2.rotation.x = Math.PI / 2;
    ringsGroup.add(ring2);

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0x0a192f, 2.5);
    scene.add(ambientLight);

    const keyLight = new THREE.PointLight(0x00f0ff, 8, 15);
    keyLight.position.set(2, 3, 4);
    scene.add(keyLight);

    const rimLight = new THREE.PointLight(0xa855f7, 6, 12);
    rimLight.position.set(-3, 2, -2);
    scene.add(rimLight);

    // 5. Mouse Parallax Gaze Vector
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener('mousemove', handleMouseMove);

    // 6. Resize Handler
    const handleResize = () => {
      if (!container) return;
      width = container.clientWidth || 500;
      height = container.clientHeight || 600;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener('resize', handleResize);

    // 7. Biological Kinematics & Render Loop
    let animationId: number;
    let clock = new THREE.Clock();

    const animate = () => {
      const elapsed = clock.getElapsedTime();

      // Smooth mouse interpolation (saccadic follow)
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;

      // Realistic 3D Head Turn towards user mouse
      headGroup.rotation.y = mouse.x * 0.45;
      headGroup.rotation.x = -mouse.y * 0.3;

      // Eyes micro-saccade tracking
      leftEye.position.x = -0.32 + mouse.x * 0.05;
      leftEye.position.y = 0.1 + mouse.y * 0.04;
      rightEye.position.x = 0.32 + mouse.x * 0.05;
      rightEye.position.y = 0.1 + mouse.y * 0.04;

      // Eye blink cycle: every ~4 seconds blink for 120ms
      const blinkCycle = elapsed % 4.2;
      if (blinkCycle < 0.14) {
        leftEye.scale.y = 0.1;
        rightEye.scale.y = 0.1;
      } else {
        leftEye.scale.y = 1.3;
        rightEye.scale.y = 1.3;
      }

      // Continuous natural breathing (sinusoidal torso deformation)
      const breath = Math.sin(elapsed * 1.5) * 0.04;
      torsoMesh.scale.set(1 + breath * 0.5, 1 + breath, 1 + breath * 0.5);
      holoEntity.position.y = Math.sin(elapsed * 1.2) * 0.08;

      // Rotating holographic floor rings
      ring1.rotation.z += 0.008;
      ring2.rotation.z -= 0.005;

      // State reactive behavior (Thinking violet pulse, speaking wave)
      if (state === 'thinking') {
        holoMaterial.color.setHex(0xa855f7);
        holoMaterial.emissive.setHex(0x9333ea);
        headGroup.position.y = 0.85 + Math.sin(elapsed * 8) * 0.02; // Thinking micro-jitter
      } else if (state === 'speaking') {
        const pulse = 0.6 + Math.sin(elapsed * 12) * 0.3;
        holoMaterial.emissiveIntensity = pulse;
        keyLight.intensity = 8 + pulse * 4;
      } else {
        holoMaterial.color.setHex(0x00f0ff);
        holoMaterial.emissive.setHex(0x00f0ff);
        holoMaterial.emissiveIntensity = 0.6;
      }

      renderer.render(scene, camera);
      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationId);
      renderer.dispose();
    };
  }, [state]);

  return (
    <div
      ref={containerRef}
      className={`holo-3d-viewport ${className}`}
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        pointerEvents: 'none',
      }}
    />
  );
}

