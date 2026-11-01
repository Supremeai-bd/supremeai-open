import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

interface Holographic3DProps {
  state?: 'idle' | 'listening' | 'thinking' | 'speaking';
  className?: string;
  /**
   * Optional rigged GLTF/GLB avatar URL. When it loads, the procedural
   * head/torso is swapped for the rigged model and its mouth morph
   * targets drive lip sync. Any load error keeps the procedural hologram.
   */
  avatarUrl?: string;
  /**
   * Optional TTS audio element or mic stream. When provided, a Web Audio
   * AnalyserNode measures real amplitude to drive the mouth (true
   * audio-driven lip sync). Without it the procedural viseme rhythm runs.
   */
  audioTarget?: MediaStream | HTMLMediaElement | null;
}

// ---------------------------------------------------------------------------
// Realism upgrade (2026-11-01). Changes over the previous build:
//   1. Post-processed bloom (UnrealBloomPass) - emissive glow now actually
//      blooms like projected light instead of flat shading.
//   2. Fresnel rim shader on the head/torso - edge-lit phosphor look.
//   3. Randomized blink cycle (was a fixed 4.2s loop = robotic).
//   4. Idle micro-behaviors: random gaze-away, head-tilt drift, weight sway.
//   5. Volumetric emitter light cone + drifting dust particles inside it.
//   6. Subtle scanline flicker on the entity (phosphor refresh artifact).
//   7. Speaking state drives a mouth bar + key light pulse (proto lip-sync;
//      real audio analysis is deferred until TTS audio is routable).
// Contract preserved: same props, same container class, pointerEvents none.
// ---------------------------------------------------------------------------
export default function Holographic3D({
  state = 'idle',
  className = '',
  avatarUrl = '',
  audioTarget = null,
}: Holographic3DProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // Live ref so audio-target identity changes never rebuild the scene.
  const audioTargetRef = useRef<MediaStream | HTMLMediaElement | null>(audioTarget);
  audioTargetRef.current = audioTarget;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let width = container.clientWidth || 500;
    let height = container.clientHeight || 600;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0.3, 7.5);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // Post-processing: bloom makes the emissive surfaces read as projected light.
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(width, height), 0.9, 0.55, 0.25);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());

    // ----- Fresnel rim material (edge-lit hologram phosphor) -----
    const fresnelMaterial = () =>
      new THREE.ShaderMaterial({
        uniforms: {
          uColor: { value: new THREE.Color(0x00f0ff) },
          uRimColor: { value: new THREE.Color(0x8ef7ff) },
          uPower: { value: 2.2 },
          uOpacity: { value: 0.85 },
          uTime: { value: 0 },
        },
        vertexShader: `
          varying vec3 vNormal;
          varying vec3 vViewDir;
          void main() {
            vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
            vNormal = normalize(normalMatrix * normal);
            vViewDir = normalize(-mvPosition.xyz);
            gl_Position = projectionMatrix * mvPosition;
          }
        `,
        fragmentShader: `
          uniform vec3 uColor;
          uniform vec3 uRimColor;
          uniform float uPower;
          uniform float uOpacity;
          uniform float uTime;
          varying vec3 vNormal;
          varying vec3 vViewDir;
          void main() {
            float fresnel = pow(1.0 - max(dot(normalize(vNormal), normalize(vViewDir)), 0.0), uPower);
            // scanline flicker: faint horizontal bands drifting upward
            float scan = 0.92 + 0.08 * sin(vViewDir.y * 40.0 - uTime * 2.0);
            vec3 col = mix(uColor * 0.35, uRimColor, fresnel) * scan;
            gl_FragColor = vec4(col, uOpacity * (0.55 + fresnel * 0.45));
          }
        `,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });

    const holoEntity = new THREE.Group();
    scene.add(holoEntity);

    const torsoMat = fresnelMaterial();
    const torsoMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.9, 1.8, 32, 1, true), torsoMat);
    torsoMesh.position.y = -1.2;
    holoEntity.add(torsoMesh);

    const neckMat = fresnelMaterial();
    const neckMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.32, 0.6, 24, 1, true), neckMat);
    neckMesh.position.y = 0.05;
    holoEntity.add(neckMesh);

    const headGroup = new THREE.Group();
    headGroup.position.y = 0.8;
    holoEntity.add(headGroup);

    const headMat = fresnelMaterial();
    const headGeo = new THREE.SphereGeometry(0.85, 48, 48);
    headGeo.scale(1.0, 1.15, 1.05);
    headGroup.add(new THREE.Mesh(headGeo, headMat));

    // Inner core sphere so the head reads as a volume, not a hollow shell.
    const coreMat = new THREE.MeshBasicMaterial({ color: 0x00f0ff, transparent: true, opacity: 0.08 });
    headGroup.add(new THREE.Mesh(new THREE.SphereGeometry(0.7, 24, 24), coreMat));

    // Expressive eyes with pupils
    const pupilMat = new THREE.MeshBasicMaterial({ color: 0xbaffff });
    const eyeGeo = new THREE.SphereGeometry(0.14, 16, 16);
    const leftEye = new THREE.Mesh(eyeGeo, pupilMat);
    leftEye.position.set(-0.32, 0.1, 0.75);
    leftEye.scale.set(1, 1.3, 0.5);
    const rightEye = new THREE.Mesh(eyeGeo, pupilMat);
    rightEye.position.set(0.32, 0.1, 0.75);
    rightEye.scale.set(1, 1.3, 0.5);
    headGroup.add(leftEye, rightEye);

    // Mouth bar (speaking viseme stand-in)
    const mouthMat = new THREE.MeshBasicMaterial({ color: 0x66f2ff, transparent: true, opacity: 0.55 });
    const mouth = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.08, 0.05), mouthMat);
    mouth.position.set(0, -0.32, 0.72);
    headGroup.add(mouth);

    // Luminous hair strands
    const hairMat = new THREE.MeshPhysicalMaterial({
      color: 0xe0f7ff,
      emissive: 0x00e1ff,
      emissiveIntensity: 0.4,
      transparent: true,
      opacity: 0.75,
      roughness: 0.3,
    });
    const hairGroup = new THREE.Group();
    for (let i = -4; i <= 4; i++) {
      const strand = new THREE.Mesh(new THREE.ConeGeometry(0.2, 1.4, 8), hairMat);
      strand.position.set(i * 0.22, 0.55 - Math.abs(i) * 0.08, 0.5 - Math.abs(i) * 0.05);
      strand.rotation.z = -i * 0.12;
      strand.rotation.x = 0.2;
      hairGroup.add(strand);
    }
    headGroup.add(hairGroup);

    // ----- Optional rigged GLTF avatar (2026-11-01 realism WO4) -----
    // When avatarUrl loads, the procedural body is swapped for the rigged
    // model: normalized scale, hologram-tinted PBR materials, first idle
    // animation clip via AnimationMixer, and mouth morph targets discovered
    // by common naming (mouthOpen / jawOpen / viseme_aa ...).
    const avatarMouthInfluences: Array<{ mesh: THREE.Mesh; index: number }> = [];
    let avatarMixer: THREE.AnimationMixer | null = null;
    const avatarGroup = new THREE.Group();
    avatarGroup.visible = false;
    holoEntity.add(avatarGroup);
    const MOUTH_MORPH_KEYS = ['mouthopen', 'jawopen', 'viseme_aa', 'viseme_a', 'mouth_open', 'fcl_mth_a', 'a'];
    if (avatarUrl) {
      new GLTFLoader().load(
        avatarUrl,
        (gltf) => {
          const model = gltf.scene;
          const box = new THREE.Box3().setFromObject(model);
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z) || 1;
          const scale = 3.0 / maxDim;
          model.scale.setScalar(scale);
          model.position.y = 0.15 - box.min.y * scale;
          model.traverse((obj) => {
            const mesh = obj as THREE.Mesh;
            if (!mesh.isMesh) return;
            const mat = mesh.material as any;
            if (mat && mat.isMeshStandardMaterial) {
              mat.color.setHex(0x00f0ff);
              mat.emissive.setHex(0x00c8e8);
              mat.emissiveIntensity = 0.35;
              mat.transparent = true;
              mat.opacity = 0.92;
            }
            if (mesh.morphTargetDictionary) {
              for (const [name, index] of Object.entries(mesh.morphTargetDictionary)) {
                if (MOUTH_MORPH_KEYS.includes(name.toLowerCase())) {
                  avatarMouthInfluences.push({ mesh, index });
                  break;
                }
              }
            }
          });
          avatarGroup.add(model);
          if (gltf.animations.length > 0) {
            avatarMixer = new THREE.AnimationMixer(model);
            avatarMixer.clipAction(gltf.animations[0]).play();
          }
          avatarGroup.visible = true;
          torsoMesh.visible = false;
          neckMesh.visible = false;
          headGroup.visible = false;
        },
        undefined,
        () => {
          /* avatar failed to load: keep the procedural hologram */
        }
      );
    }

    // ----- Audio-driven lip sync (real amplitude analysis) -----
    // A Web Audio AnalyserNode measures the provided TTS element or mic
    // stream; RMS amplitude becomes the mouth-open value. Falls back to
    // the procedural viseme rhythm when no audio target is supplied.
    let audioContext: AudioContext | null = null;
    let analyser: AnalyserNode | null = null;
    let audioSource: MediaElementAudioSourceNode | MediaStreamAudioSourceNode | null = null;
    const sampleAmplitude = (): number | null => {
      if (!analyser) return null;
      const buf = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128;
        sum += v * v;
      }
      return Math.sqrt(sum / buf.length);
    };
    const target = audioTargetRef.current;
    if (target) {
      try {
        const AudioCtor = (window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext);
        audioContext = new AudioCtor();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.6;
        audioSource =
          target instanceof MediaStream
            ? audioContext.createMediaStreamSource(target)
            : audioContext.createMediaElementSource(target as HTMLMediaElement);
        audioSource.connect(analyser);
      } catch {
        analyser = null; // audio hook-up failed: keep the procedural viseme
      }
    }

    // ----- Volumetric emitter: rings + light cone + dust -----
    const ringsGroup = new THREE.Group();
    ringsGroup.position.y = -2.3;
    scene.add(ringsGroup);

    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00f0ff, side: THREE.DoubleSide, transparent: true, opacity: 0.6 });
    const ring1 = new THREE.Mesh(new THREE.RingGeometry(1.4, 1.48, 64), ringMat);
    ring1.rotation.x = Math.PI / 2;
    const ring2 = new THREE.Mesh(new THREE.RingGeometry(2.1, 2.18, 80), ringMat);
    ring2.rotation.x = Math.PI / 2;
    ringsGroup.add(ring1, ring2);

    const coneMat = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      transparent: true,
      opacity: 0.05,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const cone = new THREE.Mesh(new THREE.ConeGeometry(1.9, 3.6, 48, 1, true), coneMat);
    cone.position.y = -0.5;
    scene.add(cone);

    const dustCount = 90;
    const dustGeo = new THREE.BufferGeometry();
    const dustPos = new Float32Array(dustCount * 3);
    const dustSeed = new Float32Array(dustCount);
    for (let i = 0; i < dustCount; i++) {
      const r = Math.sqrt(Math.random()) * 1.6;
      const a = Math.random() * Math.PI * 2;
      dustPos[i * 3] = Math.cos(a) * r;
      dustPos[i * 3 + 1] = -2.2 + Math.random() * 3.6;
      dustPos[i * 3 + 2] = Math.sin(a) * r;
      dustSeed[i] = Math.random() * Math.PI * 2;
    }
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
    const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ color: 0x9ffaff, size: 0.035, transparent: true, opacity: 0.5 }));
    scene.add(dust);

    // ----- Lights -----
    scene.add(new THREE.AmbientLight(0x0a192f, 2.5));
    const keyLight = new THREE.PointLight(0x00f0ff, 8, 15);
    keyLight.position.set(2, 3, 4);
    scene.add(keyLight);
    const rimLight = new THREE.PointLight(0xa855f7, 6, 12);
    rimLight.position.set(-3, 2, -2);
    scene.add(rimLight);

    // ----- Interaction + idle behavior state -----
    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener('mousemove', handleMouseMove);

    const handleResize = () => {
      if (!container) return;
      width = container.clientWidth || 500;
      height = container.clientHeight || 600;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      composer.setSize(width, height);
    };
    window.addEventListener('resize', handleResize);

    // Randomized blink scheduling (fixed-period blinks read as robotic)
    let nextBlinkAt = 2.5;
    let blinkUntil = -1;
    // Idle gaze-away: occasionally look off-axis for a short moment
    let gazeAwayUntil = -1;
    let gazeAwayDir = 0;
    let nextGazeAwayAt = 5;

    let animationId = 0;
    const clock = new THREE.Clock();

    const animate = () => {
      avatarMixer?.update(clock.getDelta());
      const elapsed = clock.getElapsedTime();
      const rawAmp = sampleAmplitude();
      const speakAmp = rawAmp !== null ? Math.min(1, rawAmp * 3.2) : null;

      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;

      // Idle gaze-away windows (skipped while user is actively engaged)
      if (elapsed > nextGazeAwayAt && state === 'idle') {
        gazeAwayUntil = elapsed + 0.9 + Math.random() * 0.9;
        gazeAwayDir = (Math.random() > 0.5 ? 1 : -1) * (0.5 + Math.random() * 0.5);
        nextGazeAwayAt = elapsed + 6 + Math.random() * 7;
      }
      const isLookingAway = state === 'idle' && elapsed < gazeAwayUntil;
      const gazeX = isLookingAway ? gazeAwayDir : mouse.x * 0.45;

      // Head follows gaze with a slight lag + breathing sway
      headGroup.rotation.y = gazeX;
      headGroup.rotation.x = -mouse.y * 0.3 + Math.sin(elapsed * 0.7) * 0.015;
      headGroup.rotation.z = Math.sin(elapsed * 0.43) * 0.02; // slow head-tilt drift

      // Eye micro-saccades
      const eyeX = gazeX * 0.11;
      leftEye.position.x = -0.32 + eyeX;
      rightEye.position.x = 0.32 + eyeX;
      leftEye.position.y = 0.1 + mouse.y * 0.04;
      rightEye.position.y = 0.1 + mouse.y * 0.04;

      // Blink lifecycle
      if (blinkUntil < 0 && elapsed > nextBlinkAt) {
        blinkUntil = elapsed + 0.13;
        nextBlinkAt = elapsed + 2.5 + Math.random() * 3.5 + (Math.random() > 0.85 ? -2 : 0); // occasional double-blink
      }
      const blinking = elapsed < blinkUntil;
      const eyeScaleY = blinking ? 0.1 : 1.3;
      leftEye.scale.y = eyeScaleY;
      rightEye.scale.y = eyeScaleY;

      // Breathing + weight sway
      const breath = Math.sin(elapsed * 1.5) * 0.04;
      torsoMesh.scale.set(1 + breath * 0.5, 1 + breath, 1 + breath * 0.5);
      holoEntity.position.y = Math.sin(elapsed * 1.2) * 0.08;
      holoEntity.rotation.z = Math.sin(elapsed * 0.5) * 0.008;
      holoEntity.position.x = Math.sin(elapsed * 0.31) * 0.03;

      // Emitter rings + cone + dust
      ring1.rotation.z += 0.008;
      ring2.rotation.z -= 0.005;
      coneMat.opacity = 0.045 + Math.sin(elapsed * 1.7) * 0.012;
      const positions = dustGeo.getAttribute('position') as THREE.BufferAttribute;
      for (let i = 0; i < dustCount; i++) {
        let y = positions.getY(i) + 0.0035 + Math.sin(elapsed + dustSeed[i]) * 0.001;
        if (y > 1.4) y = -2.2;
        positions.setY(i, y);
      }
      positions.needsUpdate = true;

      // State-reactive behavior
      const entityMats = [torsoMat, neckMat, headMat];
      if (state === 'thinking') {
        entityMats.forEach((m) => {
          m.uniforms.uColor.value.setHex(0xa855f7);
          m.uniforms.uRimColor.value.setHex(0xc4a5ff);
        });
        headGroup.position.y = 0.85 + Math.sin(elapsed * 8) * 0.02;
        mouth.scale.set(1, 0.5, 1);
      } else if (state === 'speaking') {
        entityMats.forEach((m) => m.uniforms.uColor.value.setHex(0x00f0ff));
        const pulse = 0.6 + Math.sin(elapsed * 12) * 0.3;
        keyLight.intensity = 8 + pulse * 4;
        bloom.strength = 0.9 + pulse * 0.35;
        // lip sync: audio amplitude when available, else speech-like rhythm
        if (avatarMouthInfluences.length > 0) {
          const open = speakAmp ?? 0.45 + Math.abs(Math.sin(elapsed * 11)) * 0.45;
          avatarMouthInfluences.forEach(({ mesh, index }) => {
            if (mesh.morphTargetInfluences) mesh.morphTargetInfluences[index] = open;
          });
        } else {
          const viseme = speakAmp !== null ? 0.5 + speakAmp * 1.6 : 0.5 + Math.abs(Math.sin(elapsed * 11)) * 1.6;
          mouth.scale.set(1, viseme, 1);
        }
      } else {
        entityMats.forEach((m) => {
          m.uniforms.uColor.value.setHex(0x00f0ff);
          m.uniforms.uRimColor.value.setHex(0x8ef7ff);
        });
        headGroup.position.y = 0.8;
        keyLight.intensity = 8;
        bloom.strength = 0.9;
        mouth.scale.set(1, 0.6, 1);
        avatarMouthInfluences.forEach(({ mesh, index }) => {
          if (mesh.morphTargetInfluences) mesh.morphTargetInfluences[index] = 0;
        });
      }
      entityMats.forEach((m) => { m.uniforms.uTime.value = elapsed; });

      if (prefersReducedMotion) {
        composer.render();
      } else {
        composer.render();
      }
      animationId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationId);
      avatarMixer?.stopAllAction();
      try { audioSource?.disconnect(); } catch { /* already gone */ }
      try { analyser?.disconnect(); } catch { /* already gone */ }
      void audioContext?.close().catch(() => undefined);
      composer.dispose();
      scene.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        const mat = mesh.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else mat?.dispose();
      });
      renderer.dispose();
    };
  }, [state, avatarUrl]);

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
