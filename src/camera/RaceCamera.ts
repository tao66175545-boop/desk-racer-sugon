import * as THREE from 'three';
import { CameraMode } from '../types';

export class RaceCamera {
  public readonly camera: THREE.PerspectiveCamera;
  public mode: CameraMode = 'chase';

  private smoothedPos = new THREE.Vector3(0, 3, 6);
  private smoothedTarget = new THREE.Vector3(0, 0.5, 0);
  private overviewAngle = 0;

  constructor(aspect: number) {
    this.camera = new THREE.PerspectiveCamera(58, aspect, 0.08, 160);
  }

  public cycleMode(): CameraMode {
    const order: CameraMode[] = ['chase', 'hood', 'overview'];
    this.mode = order[(order.indexOf(this.mode) + 1) % order.length];
    return this.mode;
  }

  public snapToCar(carRoot: THREE.Object3D): void {
    const pos = carRoot.position;
    const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(carRoot.quaternion);
    this.smoothedPos.copy(pos).addScaledVector(forward, -3.4).add(new THREE.Vector3(0, 1.45, 0));
    this.smoothedTarget.copy(pos).addScaledVector(forward, 2.2).add(new THREE.Vector3(0, 0.45, 0));
    this.camera.position.copy(this.smoothedPos);
    this.camera.lookAt(this.smoothedTarget);
  }

  public update(
    dt: number,
    carRoot: THREE.Object3D,
    speedMps: number,
    shieldActive: boolean,
    isIntro: boolean
  ): void {
    const carPos = carRoot.position;
    const carQuat = carRoot.quaternion;
    const carForward = new THREE.Vector3(0, 0, -1).applyQuaternion(carQuat);
    const carUp = new THREE.Vector3(0, 1, 0).applyQuaternion(carQuat);

    if (isIntro || this.mode === 'overview') {
      this.overviewAngle += dt * (isIntro ? 0.22 : 0.14);
      const radius = isIntro ? 16.5 : 18.2;
      const desiredPos = new THREE.Vector3(
        Math.sin(this.overviewAngle) * radius * 0.85,
        10.2,
        Math.cos(this.overviewAngle) * radius * 0.72 + 4.5
      );
      const desiredLook = new THREE.Vector3(0.0, 1.2, 0.2);

      this.smoothedPos.lerp(desiredPos, Math.min(1, dt * 3.5));
      this.smoothedTarget.lerp(desiredLook, Math.min(1, dt * 4.5));
      this.camera.fov += (50 - this.camera.fov) * Math.min(1, dt * 6);
      this.camera.updateProjectionMatrix();
      this.camera.position.copy(this.smoothedPos);
      this.camera.lookAt(this.smoothedTarget);
      return;
    }

    if (this.mode === 'hood') {
      // Thrilling micro-scale Hood / Cockpit Cam right above #01 Sugon Cloud emblem!
      const hoodPos = carPos
        .clone()
        .addScaledVector(carUp, 0.46)
        .addScaledVector(carForward, 0.18);
      const hoodLook = hoodPos
        .clone()
        .addScaledVector(carForward, 6.0)
        .addScaledVector(carUp, -0.18);

      const targetFov = shieldActive ? 78 : 66 + Math.min(8, Math.abs(speedMps) * 0.22);
      this.camera.fov += (targetFov - this.camera.fov) * Math.min(1, dt * 8);
      this.camera.updateProjectionMatrix();

      this.camera.position.copy(hoodPos);
      this.camera.up.copy(carUp).lerp(new THREE.Vector3(0, 1, 0), 0.45).normalize();
      this.camera.lookAt(hoodLook);
      return;
    }

    // Dynamic 3D Chase Camera (adapts smoothly to 3D ramps, banked turns & boost warp!)
    this.camera.up.set(0, 1, 0);
    const blendedUp = new THREE.Vector3(0, 1, 0).lerp(carUp, 0.42).normalize();
    const distBack = shieldActive ? 3.15 : 3.45;
    const heightUp = 1.38;

    const desiredPos = carPos
      .clone()
      .addScaledVector(carForward, -distBack)
      .addScaledVector(blendedUp, heightUp);

    const desiredTarget = carPos
      .clone()
      .addScaledVector(carForward, 2.4)
      .addScaledVector(blendedUp, 0.42);

    this.smoothedPos.lerp(desiredPos, Math.min(1, dt * 11.5));
    this.smoothedTarget.lerp(desiredTarget, Math.min(1, dt * 15.0));

    const speedRatio = Math.min(1, Math.abs(speedMps) / 38.0);
    const targetFov = 56 + speedRatio * 11 + (shieldActive ? 9 : 0);
    this.camera.fov += (targetFov - this.camera.fov) * Math.min(1, dt * 7.5);
    this.camera.updateProjectionMatrix();

    this.camera.position.copy(this.smoothedPos);
    this.camera.lookAt(this.smoothedTarget);
  }

  public resize(aspect: number): void {
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  }
}
