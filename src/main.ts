import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import RAPIER from '@dimforge/rapier3d-compat';

import { TrackMetadata } from './types';
import { createGantryHoloMaterial, createNeonRailMaterial } from './shaders/customShaders';
import { EngineAudioSynth } from './audio/EngineAudioSynth';
import { RaycastVehicle, VehicleInput } from './physics/RaycastVehicle';
import { StereoShieldSystem } from './gameplay/StereoShieldSystem';
import { RaceManager } from './gameplay/RaceManager';
import { RaceCamera } from './camera/RaceCamera';
import { formatRaceTime, HUD } from './ui/HUD';

function extractWorldTriMesh(mesh: THREE.Mesh): { vertices: Float32Array; indices: Uint32Array } {
  mesh.updateMatrixWorld(true);
  const geom = mesh.geometry;
  const posAttr = geom.getAttribute('position');
  const vertices = new Float32Array(posAttr.count * 3);
  const v = new THREE.Vector3();

  for (let i = 0; i < posAttr.count; i++) {
    v.fromBufferAttribute(posAttr, i).applyMatrix4(mesh.matrixWorld);
    vertices[i * 3] = v.x;
    vertices[i * 3 + 1] = v.y;
    vertices[i * 3 + 2] = v.z;
  }

  let indices: Uint32Array;
  if (geom.index) {
    const src = geom.index.array;
    indices = new Uint32Array(src.length);
    for (let i = 0; i < src.length; i++) {
      indices[i] = src[i];
    }
  } else {
    indices = new Uint32Array(posAttr.count);
    for (let i = 0; i < posAttr.count; i++) {
      indices[i] = i;
    }
  }

  return { vertices, indices };
}

function createCheckeredLineMesh(): THREE.Mesh {
  const w = 128;
  const h = 32;
  const data = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const cx = Math.floor(x / 8);
      const cy = Math.floor(y / 8);
      const isWhite = (cx + cy) % 2 === 0;
      const idx = (y * w + x) * 4;
      const val = isWhite ? 245 : 18;
      data[idx] = val;
      data[idx + 1] = val;
      data[idx + 2] = val;
      data[idx + 3] = 255;
    }
  }
  const tex = new THREE.DataTexture(data, w, h, THREE.RGBAFormat);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.needsUpdate = true;

  const geo = new THREE.PlaneGeometry(2.34, 0.52);
  geo.rotateX(-Math.PI * 0.5);
  const mat = new THREE.MeshStandardMaterial({
    map: tex,
    roughness: 0.4,
    polygonOffset: true,
    polygonOffsetFactor: -2,
  });
  return new THREE.Mesh(geo, mat);
}

async function bootstrap(): Promise<void> {
  const container = document.getElementById('canvas-container')!;
  const audio = new EngineAudioSynth();

  let startRaceFn = () => {};
  let restartRaceFn = () => {};

  const hud = new HUD(
    () => startRaceFn(),
    () => restartRaceFn(),
    () => audio.toggleMute()
  );

  hud.setLoadingProgress(15, '正在初始化 Rapier3D WASM 三维刚体与坡道悬挂物理...');
  await RAPIER.init();
  const physicsWorld = new RAPIER.World({ x: 0.0, y: -22.0, z: 0.0 }); // Crisp RC miniature gravity scale!

  // 1. Setup Three.js WebGLRenderer + ACES Filmic + Soft Shadows + PMREM Studio Env
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.06;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a101d);
  scene.fog = new THREE.FogExp2(0x0a101d, 0.011);

  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.68;

  const raceCam = new RaceCamera(window.innerWidth / window.innerHeight);

  // Selective Bloom Post-Processing Pipeline
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, raceCam.camera));
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(window.innerWidth, window.innerHeight),
    0.26, // Crisp neon bloom strength
    0.28, // Radius
    0.95  // High HDR threshold: blooms neon rails, shield, gantry & LEDs with rich color saturation!
  );
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  // 2. Studio Lighting matching desk_reference.jpg (Golden Window Sunlight + Architect Desk Lamp + Cyber Fill)
  const hemiLight = new THREE.HemisphereLight(0xdbeafe, 0x3b2818, 0.55);
  scene.add(hemiLight);

  const windowSun = new THREE.DirectionalLight(0xfff1d6, 2.55);
  windowSun.position.set(-16.5, 14.5, 5.5);
  windowSun.castShadow = true;
  windowSun.shadow.mapSize.set(2048, 2048);
  windowSun.shadow.camera.near = 2.0;
  windowSun.shadow.camera.far = 48.0;
  windowSun.shadow.camera.left = -16;
  windowSun.shadow.camera.right = 16;
  windowSun.shadow.camera.top = 14;
  windowSun.shadow.camera.bottom = -14;
  windowSun.shadow.bias = -0.0005;
  scene.add(windowSun);

  // Warm Architect Desk Lamp SpotLight (Blender (-8.4, 4.0, 4.7) -> Three (-8.4, 4.7, -4.0))
  const deskLampSpot = new THREE.SpotLight(0xffdfa8, 26.0, 18.0, Math.PI * 0.34, 0.55, 1.4);
  deskLampSpot.position.set(-8.4, 4.65, -4.0);
  deskLampSpot.target.position.set(-6.5, 0.0, -1.2);
  scene.add(deskLampSpot, deskLampSpot.target);

  // Monitor Sugon Cyan Ambient Glow
  const monitorGlow = new THREE.PointLight(0x00d8ff, 5.5, 12.0, 1.6);
  monitorGlow.position.set(0.2, 3.6, -5.2);
  scene.add(monitorGlow);

  // 3. Load Track Metadata & High-Precision Blender 5.2 GLB Assets
  hud.setLoadingProgress(35, '正在加载赛道三维样条与碰撞体元数据...');
  const metaRes = await fetch('./data/track_metadata.json');
  const meta: TrackMetadata = await metaRes.json();

  const gltfLoader = new GLTFLoader();
  const loadGltf = (url: string) =>
    new Promise<THREE.Group>((resolve, reject) => {
      gltfLoader.load(url, (gltf) => resolve(gltf.scene), undefined, reject);
    });

  hud.setLoadingProgress(55, '正在加载房间、胡桃木桌面物件与 3D 立体交叉高架赛道 (desk_track_scene.glb)...');
  const deskScene = await loadGltf('./models/desk_track_scene.glb');
  scene.add(deskScene);
  deskScene.updateMatrixWorld(true);

  hud.setLoadingProgress(80, '正在加载红灰白涂装赛车 (race_car.glb) 与曙光云起点龙门架 (start_gantry.glb)...');
  const [carModel, gantryModel] = await Promise.all([
    loadGltf('./models/race_car.glb'),
    loadGltf('./models/start_gantry.glb'),
  ]);

  // 4. Bind Custom GLSL Neon Rail Shaders & Extract Rapier3D TriMesh Colliders from deskScene
  const neonMatCyan = createNeonRailMaterial(false);
  const neonMatRed = createNeonRailMaterial(true);

  deskScene.traverse((obj) => {
    if (!(obj as THREE.Mesh).isMesh) return;
    const mesh = obj as THREE.Mesh;

    if (mesh.name === 'Col_Track_Road') {
      mesh.visible = false;
      const { vertices, indices } = extractWorldTriMesh(mesh);
      const colDesc = RAPIER.ColliderDesc.trimesh(vertices, indices)
        .setFriction(0.85)
        .setRestitution(0.0);
      physicsWorld.createCollider(colDesc);
      return;
    }

    if (mesh.name === 'Col_Track_Wall') {
      mesh.visible = false;
      const { vertices, indices } = extractWorldTriMesh(mesh);
      const colDesc = RAPIER.ColliderDesc.trimesh(vertices, indices)
        .setFriction(0.02)
        .setFrictionCombineRule(RAPIER.CoefficientCombineRule.Min)
        .setRestitution(0.18);
      physicsWorld.createCollider(colDesc);
      return;
    }

    if (mesh.name === 'Track_Neon_Rail_L') {
      mesh.material = neonMatCyan;
      return;
    }
    if (mesh.name === 'Track_Neon_Rail_R') {
      mesh.material = neonMatRed;
      return;
    }

    // Enable crisp shadows on desk, track, and props
    if (!mesh.name.startsWith('Room_Window')) {
      mesh.castShadow = !mesh.name.startsWith('Room_');
      mesh.receiveShadow = true;
    }
  });

  // Add Walnut Desk Top static physics collider so knocked stationery props bounce across the desk!
  physicsWorld.createCollider(
    RAPIER.ColliderDesc.cuboid(13.4, 0.26, 7.4).setTranslation(0, -0.26, 0).setFriction(0.6).setRestitution(0.35)
  );

  // 5. Place Start/Finish "曙光云" Logo Gantry & Bind Custom GLSL Hologram Curtain
  const sgPos = new THREE.Vector3(...meta.startGantry.pos);
  const sgTan = new THREE.Vector3(...meta.startGantry.tangent).normalize();
  const sgUp = new THREE.Vector3(...meta.startGantry.up).normalize();
  const sgRight = new THREE.Vector3().crossVectors(sgTan, sgUp).normalize();
  const sgOrthoUp = new THREE.Vector3().crossVectors(sgRight, sgTan).normalize();
  const sgBasis = new THREE.Matrix4().makeBasis(sgRight, sgOrthoUp, sgTan.clone().negate());

  gantryModel.position.copy(sgPos);
  gantryModel.quaternion.setFromRotationMatrix(sgBasis);
  gantryModel.traverse((obj) => {
    if ((obj as THREE.Mesh).isMesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
    }
  });

  const holoMat = createGantryHoloMaterial();
  const holoCurtain = gantryModel.getObjectByName('Gantry_Holo_Curtain') as THREE.Mesh | undefined;
  if (holoCurtain) {
    holoCurtain.material = holoMat;
  }
  scene.add(gantryModel);

  // Add crisp Checkered Start/Finish Line on tarmac right under Gantry
  const finishLine = createCheckeredLineMesh();
  finishLine.position.copy(sgPos).addScaledVector(sgOrthoUp, 0.014);
  finishLine.quaternion.setFromRotationMatrix(sgBasis);
  scene.add(finishLine);

  // 6. Initialize Red-Gray-White Race Car, 4-Wheel Suspension Vehicle & Stereo Confidential Shield
  carModel.traverse((obj) => {
    if ((obj as THREE.Mesh).isMesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
    }
  });

  const vehicle = new RaycastVehicle(physicsWorld, carModel, meta.carSpawn);
  scene.add(vehicle.root);
  raceCam.snapToCar(vehicle.root);

  const stereoShield = new StereoShieldSystem(
    scene,
    physicsWorld,
    vehicle.root,
    meta.cryptoNodes,
    meta.boostPads,
    meta.dynamicProps
  );

  const raceManager = new RaceManager(meta, gantryModel);

  // Wire Gameplay & Audio Events
  stereoShield.onPickupCollected = () => {
    audio.playCryptoPickup();
  };
  stereoShield.onShieldActivated = () => {
    audio.playShieldActivate();
    hud.showToast('🛡️ 【立体密算】五层可信全息护盾已展开 · 超频推进 +45%！', 2.4);
  };
  stereoShield.onPropDeflected = () => {
    audio.playImpact(0.55, true);
  };

  vehicle.onHardLanding = (intensity) => {
    audio.playImpact(intensity, stereoShield.isActive);
    stereoShield.emitSparks(vehicle.root.position, 14);
  };
  vehicle.onWallScrape = (localHit, intensity) => {
    audio.playImpact(intensity, stereoShield.isActive);
    if (stereoShield.isActive) {
      stereoShield.triggerImpactRipple(localHit, vehicle.root.position);
    } else {
      stereoShield.emitSparks(vehicle.root.position, 8);
    }
  };

  raceManager.onCountdownBeep = (isGo) => {
    audio.playCountdownTone(isGo);
    if (isGo) {
      hud.triggerGoBanner();
    }
  };
  raceManager.onLapCompleted = (lapNum, lapMs, isBest) => {
    audio.playCryptoPickup();
    hud.showToast(
      `🏁 第 ${lapNum} 圈完成：${formatRaceTime(lapMs)}${isBest ? '  ★ 新最快单圈纪录！' : ''}`,
      2.8
    );
  };
  raceManager.onRaceFinished = (totalMs, bestMs) => {
    audio.playShieldActivate();
    hud.showFinishSummary(totalMs, bestMs, raceManager.lapHistoryMs);
  };

  // 7. Keyboard Input Handling
  const keys = new Set<string>();
  window.addEventListener('keydown', (e) => {
    keys.add(e.code);
    if (raceManager.phase !== 'intro') {
      audio.init();
    }

    if (e.code === 'ShiftLeft' || e.code === 'ShiftRight' || e.code === 'KeyE') {
      if (raceManager.phase === 'racing') {
        stereoShield.tryActivate();
      }
    } else if (e.code === 'KeyC') {
      const nextMode = raceCam.cycleMode();
      hud.setCameraBadge(nextMode);
    } else if (e.code === 'KeyV') {
      hud.toggleRefPip();
    } else if (e.code === 'KeyM') {
      const muted = audio.toggleMute();
      hud.updateMuteIcon(muted);
    } else if (e.code === 'KeyR' && (raceManager.phase === 'racing' || raceManager.phase === 'countdown')) {
      vehicle.resetToPose(raceManager.getRespawnPose());
      hud.showToast('↺ 已复位至最近检查点', 1.5);
    }
  });

  window.addEventListener('keyup', (e) => {
    keys.delete(e.code);
  });

  startRaceFn = () => {
    audio.init();
    raceCam.mode = 'chase';
    hud.setCameraBadge('chase');
    vehicle.resetToPose(meta.carSpawn);
    stereoShield.resetPropsAndEnergy();
    raceManager.startCountdown();
  };

  restartRaceFn = () => {
    startRaceFn();
  };

  window.addEventListener('resize', () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h);
    composer.setSize(w, h);
    bloomPass.resolution.set(w, h);
    raceCam.resize(w / h);
  });

  hud.setLoadingProgress(100, '准备就绪！');
  hud.showIntro(meta);

  // Expose lightweight debug telemetry handle on window for automated verification
  (window as unknown as Record<string, unknown>).__DESK_RACER__ = {
    vehicle,
    stereoShield,
    raceManager,
    raceCam,
    startRace: () => {
      document.getElementById('btn-start-race')?.click();
    },
  };

  // 8. Fixed-Timestep Physics + High-Refresh Render Loop
  const fixedDt = 1 / 120;
  physicsWorld.timestep = fixedDt;
  let accumulator = 0;
  let prevTime = performance.now() * 0.001;
  let elapsed = 0;

  function animate(): void {
    requestAnimationFrame(animate);

    const now = performance.now() * 0.001;
    const frameDt = Math.min(0.05, Math.max(0.001, now - prevTime));
    prevTime = now;
    elapsed += frameDt;

    const input: VehicleInput = {
      forward: keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0,
      brake: keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0,
      steer:
        (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0) -
        (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0),
      handbrake: keys.has('Space'),
    };

    const controlsLocked = raceManager.phase !== 'racing';

    accumulator += frameDt;
    let subSteps = 0;
    while (accumulator >= fixedDt && subSteps < 6) {
      vehicle.stepPhysics(fixedDt, input, controlsLocked, stereoShield.isActive);
      physicsWorld.step();
      accumulator -= fixedDt;
      subSteps++;
    }

    // Safety auto-recovery if car ever drops off desk edge
    if (vehicle.root.position.y < -1.8) {
      vehicle.resetToPose(raceManager.getRespawnPose());
      hud.showToast('↺ 驶出桌面，自动安全复位', 1.6);
    }

    const carForward = new THREE.Vector3(0, 0, -1).applyQuaternion(vehicle.root.quaternion);
    const isDrifting = input.handbrake && Math.abs(vehicle.forwardSpeed) > 6.0 && vehicle.groundedWheels > 0;

    const { hitBoostPad } = stereoShield.update(
      frameDt,
      elapsed,
      vehicle.root.position,
      carForward,
      controlsLocked ? 0 : input.forward,
      isDrifting,
      vehicle.forwardSpeed
    );
    if (hitBoostPad && raceManager.phase === 'racing') {
      vehicle.triggerBoostPad(0.95);
    }

    raceManager.update(frameDt, vehicle.root.position, carForward, vehicle.forwardSpeed);

    // Update Custom GLSL Uniforms
    const boostVisual = stereoShield.isActive ? 1.0 : vehicle.boostPadTimer > 0 ? 0.65 : 0.0;
    neonMatCyan.uniforms.uTime.value = elapsed;
    neonMatCyan.uniforms.uBoostFactor.value = boostVisual;
    neonMatRed.uniforms.uTime.value = elapsed;
    neonMatRed.uniforms.uBoostFactor.value = boostVisual;

    holoMat.uniforms.uTime.value = elapsed;
    holoMat.uniforms.uLapFlash.value = raceManager.lapFlash;

    // Update Audio, Camera & HUD
    audio.update(
      frameDt,
      vehicle.forwardSpeed,
      controlsLocked ? 0.15 : input.forward,
      vehicle.lateralSlip,
      vehicle.groundedWheels > 0,
      stereoShield.isActive
    );

    raceCam.update(
      frameDt,
      vehicle.root,
      vehicle.forwardSpeed,
      stereoShield.isActive,
      raceManager.phase === 'intro'
    );

    hud.update(
      frameDt,
      raceManager.phase,
      raceManager.countdownValue,
      raceManager.currentLap,
      raceManager.totalLaps,
      raceManager.currentLapMs,
      raceManager.bestLapMs,
      raceManager.isWrongWay,
      vehicle.forwardSpeed,
      audio.currentRpm,
      audio.currentGear,
      vehicle.groundedWheels,
      isDrifting,
      stereoShield.energy,
      stereoShield.isActive,
      vehicle.root.position,
      carForward
    );

    composer.render();
  }

  animate();
}

bootstrap().catch((err) => {
  console.error('Desk Racer initialization error:', err);
  const statusEl = document.getElementById('loading-status');
  if (statusEl) {
    statusEl.textContent = `加载出错: ${err instanceof Error ? err.message : String(err)}`;
    statusEl.style.color = '#ff3855';
  }
});
