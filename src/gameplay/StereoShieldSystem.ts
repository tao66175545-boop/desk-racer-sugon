import * as THREE from 'three';
import RAPIER from '@dimforge/rapier3d-compat';
import { BoostPadData, CryptoNodeData, DynamicPropData } from '../types';
import { createBoostPadMaterial, createStereoShieldMaterial } from '../shaders/customShaders';

interface CryptoPickupInstance {
  id: number;
  basePos: THREE.Vector3;
  group: THREE.Group;
  coreMesh: THREE.Mesh;
  ringMesh: THREE.Mesh;
  respawnTimer: number;
}

interface DynamicPropInstance {
  body: RAPIER.RigidBody;
  mesh: THREE.Mesh;
  initialPos: THREE.Vector3;
}

/**
 * Manages Sugon Cloud's "立体密算 (Stereo Confidential Computing)" Shield & Overdrive Boost System:
 *  - 5-Layer Confidential Energy Gauge (0..100, 20 per layer L1..L5)
 *  - Floating Encrypted Compute Cube pickups & Track Chevron Boost Pads
 *  - Custom GLSL 3D Hexagonal Confidential Shield around the Race Car + Impact Ripples
 *  - Twin Exhaust Plasma Cones & Spark Burst Particle Pool
 *  - Electromagnetic Knockback Wave against dynamic desk stationery obstacles!
 */
export class StereoShieldSystem {
  public energy = 60;             // Start race with 3 layers (60%) ready to test immediately!
  public readonly maxEnergy = 100;
  public isActive = false;

  private shieldMesh: THREE.Mesh;
  private shieldMat: THREE.ShaderMaterial;
  private boostPadMat: THREE.ShaderMaterial;
  private flameMeshes: THREE.Mesh[] = [];
  private flameMat: THREE.MeshBasicMaterial;

  private cryptoPickups: CryptoPickupInstance[] = [];
  private boostPads: Array<{ pos: THREE.Vector3; radius: number }> = [];
  private dynamicProps: DynamicPropInstance[] = [];

  // Particle burst system for pickups & shield deflections
  private sparkPoints: THREE.Points;
  private sparkPositions: Float32Array;
  private sparkVelocities: Float32Array;
  private sparkLife: Float32Array;
  private readonly maxSparks = 140;
  private sparkCursor = 0;

  private hitAge = 10.0;

  public onPickupCollected: (() => void) | null = null;
  public onShieldActivated: (() => void) | null = null;
  public onPropDeflected: (() => void) | null = null;

  constructor(
    scene: THREE.Scene,
    world: RAPIER.World,
    carRoot: THREE.Object3D,
    cryptoData: CryptoNodeData[],
    boostPadData: BoostPadData[],
    dynPropData: DynamicPropData[]
  ) {
    // 1. 3D Aerodynamic Stereo Confidential Shield Shell attached to Car
    this.shieldMat = createStereoShieldMaterial();
    const shieldGeo = new THREE.SphereGeometry(1.0, 36, 24);
    shieldGeo.scale(0.58, 0.39, 1.06);
    this.shieldMesh = new THREE.Mesh(shieldGeo, this.shieldMat);
    this.shieldMesh.position.set(0, 0.25, 0.0);
    this.shieldMesh.visible = false;
    carRoot.add(this.shieldMesh);

    // 2. Twin Rear Exhaust Plasma Flames (at Car local x = ±0.13, y = 0.155, z = +0.86)
    this.flameMat = new THREE.MeshBasicMaterial({
      color: 0xff3b1f,
      transparent: true,
      opacity: 0.0,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const coneGeo = new THREE.ConeGeometry(0.048, 0.42, 14);
    coneGeo.rotateX(Math.PI * 0.5); // Tip points +Z (backward out of exhaust!)
    for (const sx of [-0.13, 0.13]) {
      const fMesh = new THREE.Mesh(coneGeo, this.flameMat);
      fMesh.position.set(sx, 0.155, 1.02);
      carRoot.add(fMesh);
      this.flameMeshes.push(fMesh);
    }

    // 3. Build 5 Glowing Chevron Boost Pads on the 3D Track
    this.boostPadMat = createBoostPadMaterial();
    const padGeo = new THREE.PlaneGeometry(1.65, 2.50);
    padGeo.rotateX(-Math.PI * 0.5); // Flat on XZ, vUv.y=1 points toward -Z (Forward)

    for (const bp of boostPadData) {
      const pos = new THREE.Vector3(...bp.pos);
      const tangent = new THREE.Vector3(...bp.tangent).normalize();
      const up = new THREE.Vector3(...bp.up).normalize();
      const right = new THREE.Vector3().crossVectors(tangent, up).normalize();
      const orthoUp = new THREE.Vector3().crossVectors(right, tangent).normalize();

      const padMesh = new THREE.Mesh(padGeo, this.boostPadMat);
      padMesh.position.copy(pos);
      const basis = new THREE.Matrix4().makeBasis(right, orthoUp, tangent.clone().negate());
      padMesh.quaternion.setFromRotationMatrix(basis);
      scene.add(padMesh);

      this.boostPads.push({ pos, radius: 1.45 });
    }

    // 4. Build 16 Floating "密态算力块 (Encrypted Compute Cubes)"
    const coreGeo = new THREE.OctahedronGeometry(0.22, 0);
    const ringGeo = new THREE.TorusGeometry(0.32, 0.022, 8, 6); // Hexagonal security torus!
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x00f0ff,
      emissive: 0x00c8ff,
      emissiveIntensity: 2.2,
      roughness: 0.1,
      metalness: 0.8,
    });
    const ringMat = new THREE.MeshStandardMaterial({
      color: 0xff1838,
      emissive: 0xff1430,
      emissiveIntensity: 1.8,
      roughness: 0.2,
      metalness: 0.9,
    });

    for (const cn of cryptoData) {
      const grp = new THREE.Group();
      const basePos = new THREE.Vector3(...cn.pos);
      grp.position.copy(basePos);

      const coreMesh = new THREE.Mesh(coreGeo, coreMat);
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      grp.add(coreMesh, ringMesh);
      scene.add(grp);

      this.cryptoPickups.push({
        id: cn.id,
        basePos,
        group: grp,
        coreMesh,
        ringMesh,
        respawnTimer: 0,
      });
    }

    // 5. Spawn Dynamic Knockable Desk Stationery Props (Keycaps, Dice, Erasers, Mini Energy Cans)
    this.spawnDynamicProps(scene, world, dynPropData);

    // 6. Initialize GPU Spark Burst Pool with soft radial glow sprite texture
    this.sparkPositions = new Float32Array(this.maxSparks * 3);
    this.sparkVelocities = new Float32Array(this.maxSparks * 3);
    this.sparkLife = new Float32Array(this.maxSparks);

    const spriteSize = 32;
    const spriteData = new Uint8Array(spriteSize * spriteSize * 4);
    for (let y = 0; y < spriteSize; y++) {
      for (let x = 0; x < spriteSize; x++) {
        const dx = (x / (spriteSize - 1)) * 2 - 1;
        const dy = (y / (spriteSize - 1)) * 2 - 1;
        const r2 = dx * dx + dy * dy;
        const a = r2 > 1.0 ? 0 : Math.exp(-r2 * 4.2);
        const idx = (y * spriteSize + x) * 4;
        spriteData[idx] = 255;
        spriteData[idx + 1] = 255;
        spriteData[idx + 2] = 255;
        spriteData[idx + 3] = Math.round(a * 255);
      }
    }
    const sparkTex = new THREE.DataTexture(spriteData, spriteSize, spriteSize, THREE.RGBAFormat);
    sparkTex.needsUpdate = true;

    const sparkGeo = new THREE.BufferGeometry();
    sparkGeo.setAttribute('position', new THREE.BufferAttribute(this.sparkPositions, 3));
    const sparkMat = new THREE.PointsMaterial({
      color: 0x38f6ff,
      map: sparkTex,
      size: 0.13,
      transparent: true,
      opacity: 0.92,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.sparkPoints = new THREE.Points(sparkGeo, sparkMat);
    this.sparkPoints.frustumCulled = false;
    scene.add(this.sparkPoints);
  }

  private spawnDynamicProps(scene: THREE.Scene, world: RAPIER.World, dynPropData: DynamicPropData[]): void {
    const mats: Record<DynamicPropData['kind'], THREE.MeshStandardMaterial> = {
      keycap_red: new THREE.MeshStandardMaterial({ color: 0xdc0018, roughness: 0.35, metalness: 0.1 }),
      keycap_cyan: new THREE.MeshStandardMaterial({ color: 0x00d8f5, emissive: 0x004466, roughness: 0.3, metalness: 0.2 }),
      dice: new THREE.MeshStandardMaterial({ color: 0xf4f6fa, roughness: 0.2, metalness: 0.05 }),
      eraser: new THREE.MeshStandardMaterial({ color: 0xff9f1c, roughness: 0.65 }),
      energy_can: new THREE.MeshStandardMaterial({ color: 0x1a5cff, roughness: 0.22, metalness: 0.85 }),
    };

    const boxGeo = new THREE.BoxGeometry(0.24, 0.22, 0.24);
    const eraserGeo = new THREE.BoxGeometry(0.32, 0.14, 0.20);
    const canGeo = new THREE.CylinderGeometry(0.12, 0.12, 0.38, 16);

    for (const dp of dynPropData) {
      const initPos = new THREE.Vector3(...dp.pos);
      const geo = dp.kind === 'energy_can' ? canGeo : dp.kind === 'eraser' ? eraserGeo : boxGeo;
      const mesh = new THREE.Mesh(geo, mats[dp.kind]);
      mesh.castShadow = true;
      mesh.position.copy(initPos);
      scene.add(mesh);

      const rb = world.createRigidBody(
        RAPIER.RigidBodyDesc.dynamic()
          .setTranslation(initPos.x, initPos.y, initPos.z)
          .setLinearDamping(0.6)
          .setAngularDamping(0.8)
      );
      const col = dp.kind === 'energy_can'
        ? RAPIER.ColliderDesc.cylinder(0.19, 0.12)
        : RAPIER.ColliderDesc.cuboid(0.12, 0.11, 0.12);
      col.setMass(0.45).setRestitution(0.45).setFriction(0.5);
      world.createCollider(col, rb);

      this.dynamicProps.push({ body: rb, mesh, initialPos: initPos });
    }
  }

  public resetPropsAndEnergy(): void {
    this.energy = 60;
    this.isActive = false;
    this.shieldMesh.visible = false;
    for (const cp of this.cryptoPickups) {
      cp.respawnTimer = 0;
      cp.group.visible = true;
    }
    for (const dp of this.dynamicProps) {
      dp.body.setTranslation({ x: dp.initialPos.x, y: dp.initialPos.y, z: dp.initialPos.z }, true);
      dp.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
      dp.body.setAngvel({ x: 0, y: 0, z: 0 }, true);
    }
  }

  public tryActivate(): boolean {
    if (this.isActive) return true;
    if (this.energy >= 20) {
      this.isActive = true;
      this.shieldMesh.visible = true;
      this.hitAge = 0.0;
      this.shieldMat.uniforms.uHitLocalPos.value.set(0, 0.25, -0.9);
      if (this.onShieldActivated) this.onShieldActivated();
      return true;
    }
    return false;
  }

  public triggerImpactRipple(localPos: THREE.Vector3, worldBurstOrigin?: THREE.Vector3): void {
    this.hitAge = 0.0;
    this.shieldMat.uniforms.uHitLocalPos.value.copy(localPos);
    if (worldBurstOrigin) {
      this.emitSparks(worldBurstOrigin, 18);
    }
  }

  public emitSparks(origin: THREE.Vector3, count = 16): void {
    for (let i = 0; i < count; i++) {
      const idx = this.sparkCursor;
      this.sparkCursor = (this.sparkCursor + 1) % this.maxSparks;
      const i3 = idx * 3;
      this.sparkPositions[i3] = origin.x + (Math.random() - 0.5) * 0.25;
      this.sparkPositions[i3 + 1] = origin.y + Math.random() * 0.25;
      this.sparkPositions[i3 + 2] = origin.z + (Math.random() - 0.5) * 0.25;

      this.sparkVelocities[i3] = (Math.random() - 0.5) * 7.5;
      this.sparkVelocities[i3 + 1] = 2.0 + Math.random() * 5.5;
      this.sparkVelocities[i3 + 2] = (Math.random() - 0.5) * 7.5;
      this.sparkLife[idx] = 0.45 + Math.random() * 0.35;
    }
  }

  public update(
    dt: number,
    elapsed: number,
    carWorldPos: THREE.Vector3,
    carForward: THREE.Vector3,
    throttle: number,
    isDrifting: boolean,
    speedMps: number
  ): { hitBoostPad: boolean } {
    this.boostPadMat.uniforms.uTime.value = elapsed;

    // Drift clean recharge (+6.5% / sec while drifting at speed!)
    if (!this.isActive && isDrifting && Math.abs(speedMps) > 7.0) {
      this.energy = Math.min(this.maxEnergy, this.energy + dt * 7.5);
    }

    // Drain Stereo Confidential Shield while active
    if (this.isActive) {
      this.energy -= dt * 17.5;
      if (this.energy <= 0) {
        this.energy = 0;
        this.isActive = false;
      }
    }

    const targetStrength = this.isActive ? 1.0 : 0.0;
    const curStrength = this.shieldMat.uniforms.uStrength.value as number;
    const nextStrength = curStrength + (targetStrength - curStrength) * Math.min(1, dt * 10.0);
    this.shieldMat.uniforms.uStrength.value = nextStrength;
    this.shieldMat.uniforms.uTime.value = elapsed;
    this.hitAge += dt;
    this.shieldMat.uniforms.uHitAge.value = this.hitAge;
    this.shieldMesh.visible = nextStrength > 0.01;

    // Update Twin Exhaust Plasma Flames
    const flameScale = this.isActive
      ? 1.25 + Math.sin(elapsed * 45.0) * 0.25
      : throttle > 0.1
        ? 0.45 + throttle * 0.45 + Math.sin(elapsed * 35.0) * 0.12
        : 0.0;
    this.flameMat.color.setHex(this.isActive ? 0x00f0ff : 0xff3b18);
    this.flameMat.opacity = flameScale > 0.05 ? Math.min(0.92, flameScale * 0.78) : 0.0;
    for (const fm of this.flameMeshes) {
      fm.scale.set(1, 1, Math.max(0.01, flameScale));
    }

    // Check Boost Pads
    let hitBoostPad = false;
    for (const bp of this.boostPads) {
      if (carWorldPos.distanceToSquared(bp.pos) < bp.radius * bp.radius) {
        hitBoostPad = true;
        this.energy = Math.min(this.maxEnergy, this.energy + dt * 22.0);
      }
    }

    // Update & Collect Floating Encrypted Compute Cubes
    for (const cp of this.cryptoPickups) {
      if (cp.respawnTimer > 0) {
        cp.respawnTimer -= dt;
        if (cp.respawnTimer <= 0) {
          cp.group.visible = true;
        }
        continue;
      }

      cp.group.position.y = cp.basePos.y + Math.sin(elapsed * 3.4 + cp.id) * 0.09;
      cp.coreMesh.rotation.y = elapsed * 2.2 + cp.id;
      cp.coreMesh.rotation.x = elapsed * 1.3;
      cp.ringMesh.rotation.z = -elapsed * 2.8;
      cp.ringMesh.rotation.x = Math.sin(elapsed * 1.7 + cp.id) * 0.65;

      if (carWorldPos.distanceToSquared(cp.group.position) < 1.15 * 1.15) {
        cp.respawnTimer = 9.0;
        cp.group.visible = false;
        this.energy = Math.min(this.maxEnergy, this.energy + 24);
        this.emitSparks(cp.group.position, 22);
        if (this.onPickupCollected) this.onPickupCollected();
      }
    }

    // Sync Dynamic Knockable Desk Props & Electromagnetic Shield Repulsion!
    for (const dp of this.dynamicProps) {
      const t = dp.body.translation();
      const r = dp.body.rotation();
      dp.mesh.position.set(t.x, t.y, t.z);
      dp.mesh.quaternion.set(r.x, r.y, r.z, r.w);

      // Respawn prop if knocked completely off the desk into the abyss
      if (t.y < -6.5) {
        dp.body.setTranslation({ x: dp.initialPos.x, y: dp.initialPos.y + 0.5, z: dp.initialPos.z }, true);
        dp.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
      }

      // Active Stereo Confidential Shield Electromagnetic Repulsion!
      if (this.isActive) {
        const dx = t.x - carWorldPos.x;
        const dy = t.y - carWorldPos.y;
        const dz = t.z - carWorldPos.z;
        const dSq = dx * dx + dy * dy + dz * dz;
        if (dSq < 2.35 * 2.35 && dSq > 0.01) {
          const invD = 1.0 / Math.sqrt(dSq);
          const pushX = dx * invD * 6.5 + carForward.x * 4.5;
          const pushZ = dz * invD * 6.5 + carForward.z * 4.5;
          dp.body.applyImpulse({ x: pushX, y: 3.8, z: pushZ }, true);
          dp.body.applyTorqueImpulse({ x: 0.4, y: 0.6, z: -0.3 }, true);
          this.triggerImpactRipple(new THREE.Vector3(0, 0.25, -0.85), dp.mesh.position);
          if (this.onPropDeflected) this.onPropDeflected();
        }
      }
    }

    // Step Spark Particles
    const posAttr = this.sparkPoints.geometry.getAttribute('position') as THREE.BufferAttribute;
    for (let i = 0; i < this.maxSparks; i++) {
      const i3 = i * 3;
      if (this.sparkLife[i] > 0) {
        this.sparkLife[i] -= dt;
        this.sparkPositions[i3] += this.sparkVelocities[i3] * dt;
        this.sparkPositions[i3 + 1] += this.sparkVelocities[i3 + 1] * dt;
        this.sparkPositions[i3 + 2] += this.sparkVelocities[i3 + 2] * dt;
        this.sparkVelocities[i3 + 1] -= 9.8 * dt;
        if (this.sparkLife[i] <= 0) {
          this.sparkPositions[i3 + 1] = -999;
        }
      } else {
        this.sparkPositions[i3 + 1] = -999;
      }
    }
    posAttr.needsUpdate = true;

    return { hitBoostPad };
  }

  public get activeLayers(): number {
    return Math.floor(this.energy / 20);
  }
}
