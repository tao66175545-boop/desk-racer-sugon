import * as THREE from 'three';
import RAPIER from '@dimforge/rapier3d-compat';
import { PoseData } from '../types';

export interface VehicleInput {
  forward: number;   // 0..1
  brake: number;     // 0..1
  steer: number;     // -1 (right) .. +1 (left)
  handbrake: boolean;
}

interface WheelMount {
  name: string;
  mesh: THREE.Object3D | null;
  strutLocal: THREE.Vector3;
  restLength: number;
  radius: number;
  isFront: boolean;
  compression: number;
  prevCompression: number;
  grounded: boolean;
  spinAngle: number;
}

export class RaycastVehicle {
  public readonly root = new THREE.Group();
  public chassisVisual: THREE.Object3D | null = null;
  public body: RAPIER.RigidBody;
  public collider: RAPIER.Collider;

  private world: RAPIER.World;
  private wheels: WheelMount[] = [];

  // Telemetry state
  public forwardSpeed = 0;        // m/s (multiply by 7.2 for exhilarating scale km/h!)
  public lateralSlip = 0;         // m/s normalized
  public groundedWheels = 0;
  public currentSteerAngle = 0;
  public boostPadTimer = 0;
  public wallHitCooldown = 0;

  private wasAirborne = false;
  public onHardLanding: ((intensity: number) => void) | null = null;
  public onWallScrape: ((localHitPos: THREE.Vector3, intensity: number) => void) | null = null;

  private readonly mass = 120.0;
  private readonly springStiffness = 9800.0;
  private readonly springDamping = 1120.0;

  constructor(world: RAPIER.World, carModelRoot: THREE.Object3D, spawn: PoseData) {
    this.world = world;
    this.root.add(carModelRoot);

    this.chassisVisual = carModelRoot.getObjectByName('Car_Chassis') || null;

    const wheelSpecs: Array<{ name: string; x: number; z: number; radius: number; isFront: boolean }> = [
      { name: 'Wheel_FL', x: -0.375, z: -0.52, radius: 0.17, isFront: true },
      { name: 'Wheel_FR', x:  0.375, z: -0.52, radius: 0.17, isFront: true },
      { name: 'Wheel_RL', x: -0.385, z:  0.52, radius: 0.178, isFront: false },
      { name: 'Wheel_RR', x:  0.385, z:  0.52, radius: 0.178, isFront: false },
    ];

    for (const ws of wheelSpecs) {
      const mesh = carModelRoot.getObjectByName(ws.name) || null;
      if (mesh) {
        mesh.rotation.order = 'YXZ'; // Y = steer, X = axle roll
      }
      this.wheels.push({
        name: ws.name,
        mesh,
        strutLocal: new THREE.Vector3(ws.x, 0.42, ws.z),
        restLength: 0.42 - ws.radius,
        radius: ws.radius,
        isFront: ws.isFront,
        compression: 0,
        prevCompression: 0,
        grounded: false,
        spinAngle: 0,
      });
    }

    // Create Rapier Dynamic RigidBody
    const rbDesc = RAPIER.RigidBodyDesc.dynamic()
      .setLinearDamping(0.18)
      .setAngularDamping(2.6)
      .setCcdEnabled(true);

    this.body = world.createRigidBody(rbDesc);

    // Raised rounded bumper collider: clears steep 3D ramps cleanly while colliding smoothly with walls & props
    const colDesc = RAPIER.ColliderDesc.roundCuboid(0.37, 0.11, 0.76, 0.05)
      .setTranslation(0, 0.27, 0)
      .setMass(this.mass)
      .setFriction(0.02)
      .setFrictionCombineRule(RAPIER.CoefficientCombineRule.Min)
      .setRestitution(0.15);

    this.collider = world.createCollider(colDesc, this.body);
    this.resetToPose(spawn);
  }

  public resetToPose(pose: PoseData): void {
    const pos = new THREE.Vector3(...pose.pos);
    const tangent = new THREE.Vector3(...pose.tangent).normalize();
    const up = new THREE.Vector3(...pose.up).normalize();
    const right = new THREE.Vector3().crossVectors(tangent, up).normalize();
    const orthoUp = new THREE.Vector3().crossVectors(right, tangent).normalize();

    // Car local -Z is Forward (tangent), +Y is Up, +X is Right
    const basis = new THREE.Matrix4().makeBasis(right, orthoUp, tangent.clone().negate());
    const quat = new THREE.Quaternion().setFromRotationMatrix(basis);

    this.body.setTranslation({ x: pos.x, y: pos.y, z: pos.z }, true);
    this.body.setRotation({ x: quat.x, y: quat.y, z: quat.z, w: quat.w }, true);
    this.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
    this.body.setAngvel({ x: 0, y: 0, z: 0 }, true);

    this.forwardSpeed = 0;
    this.lateralSlip = 0;
    this.boostPadTimer = 0;
    this.syncVisuals(0.016, 0);
  }

  public triggerBoostPad(duration = 1.15): void {
    this.boostPadTimer = Math.max(this.boostPadTimer, duration);
  }

  public stepPhysics(dt: number, input: VehicleInput, controlsLocked: boolean, shieldBoostActive: boolean): void {
    if (this.boostPadTimer > 0) this.boostPadTimer = Math.max(0, this.boostPadTimer - dt);
    if (this.wallHitCooldown > 0) this.wallHitCooldown = Math.max(0, this.wallHitCooldown - dt);

    const rbPos = this.body.translation();
    const rbRot = this.body.rotation();
    const chassisPos = new THREE.Vector3(rbPos.x, rbPos.y, rbPos.z);
    const chassisQuat = new THREE.Quaternion(rbRot.x, rbRot.y, rbRot.z, rbRot.w);

    const chassisRight = new THREE.Vector3(1, 0, 0).applyQuaternion(chassisQuat);
    const chassisUp = new THREE.Vector3(0, 1, 0).applyQuaternion(chassisQuat);
    const chassisForward = new THREE.Vector3(0, 0, -1).applyQuaternion(chassisQuat);

    const linVel = this.body.linvel();
    const velVec = new THREE.Vector3(linVel.x, linVel.y, linVel.z);

    this.forwardSpeed = velVec.dot(chassisForward);
    const sideSpeed = velVec.dot(chassisRight);
    this.lateralSlip = Math.abs(sideSpeed) / Math.max(4.0, Math.abs(this.forwardSpeed));

    // Speed-sensitive steering angle
    const maxSteer = THREE.MathUtils.lerp(0.46, 0.24, Math.min(1, Math.abs(this.forwardSpeed) / 34.0));
    const targetSteer = controlsLocked ? 0 : input.steer * maxSteer;
    this.currentSteerAngle += (targetSteer - this.currentSteerAngle) * Math.min(1, dt * 13.0);

    // 1. Cast 4 Suspension Rays
    const rayDir = chassisUp.clone().negate();
    let groundedCount = 0;
    const avgRoadNormal = new THREE.Vector3();

    for (const w of this.wheels) {
      const strutWorld = w.strutLocal.clone().applyQuaternion(chassisQuat).add(chassisPos);
      const maxToi = w.restLength + w.radius + 0.12;
      const ray = new RAPIER.Ray(
        { x: strutWorld.x, y: strutWorld.y, z: strutWorld.z },
        { x: rayDir.x, y: rayDir.y, z: rayDir.z }
      );

      const hit = this.world.castRayAndGetNormal(
        ray,
        maxToi,
        true,
        undefined,
        undefined,
        this.collider,
        this.body
      );

      w.prevCompression = w.compression;
      if (hit && hit.timeOfImpact <= w.restLength + w.radius + 0.04) {
        w.grounded = true;
        groundedCount++;
        const targetDist = w.restLength + w.radius;
        w.compression = Math.max(-0.04, Math.min(0.20, targetDist - hit.timeOfImpact));

        const hitNormal = new THREE.Vector3(hit.normal.x, hit.normal.y, hit.normal.z);
        if (hitNormal.dot(chassisUp) > 0.25) {
          avgRoadNormal.add(hitNormal);
        }

        // Spring + Damper vertical suspension force
        const compVel = (w.compression - w.prevCompression) / Math.max(dt, 1e-4);
        const suspForceMag = Math.max(0, this.springStiffness * w.compression + this.springDamping * compVel);

        // Apply near chassis plane to prevent tip-overs while preserving crisp 3D ramp pitch adaptation!
        const forceAppPoint = chassisPos
          .clone()
          .addScaledVector(chassisRight, w.strutLocal.x * 0.72)
          .addScaledVector(chassisForward, -w.strutLocal.z * 0.78)
          .addScaledVector(chassisUp, 0.20);

        const suspForce = chassisUp.clone().multiplyScalar(suspForceMag * dt);
        this.body.applyImpulseAtPoint(
          { x: suspForce.x, y: suspForce.y, z: suspForce.z },
          { x: forceAppPoint.x, y: forceAppPoint.y, z: forceAppPoint.z },
          true
        );
      } else {
        w.grounded = false;
        w.compression += (0 - w.compression) * Math.min(1, dt * 10.0);
      }
    }

    // Detect hard landing from 3D ramp jump for audio & spark feedback
    if (this.wasAirborne && groundedCount >= 2) {
      const downVel = Math.max(0, -velVec.y);
      if (downVel > 2.2 && this.onHardLanding) {
        this.onHardLanding(Math.min(1.0, downVel / 9.0));
      }
    }
    this.wasAirborne = groundedCount === 0;
    this.groundedWheels = groundedCount;

    // 2. Drive, Brake, Lateral Cornering Grip & Aerodynamic Downforce
    if (groundedCount > 0 && !controlsLocked) {
      const gripFactor = groundedCount / 4.0;
      const isBoosted = shieldBoostActive || this.boostPadTimer > 0;
      const topSpeed = isBoosted ? 43.5 : 30.0; // ~313 km/h boosted vs ~216 km/h normal scale speed!
      const engineAccel = isBoosted ? 35.0 : 22.5;

      let longAccel = 0;
      if (input.forward > 0) {
        if (this.forwardSpeed < 0) {
          longAccel = 36.0 * input.forward; // Fast braking from reverse
        } else if (this.forwardSpeed < topSpeed) {
          const speedRatio = Math.max(0, this.forwardSpeed / topSpeed);
          longAccel = engineAccel * (1.0 - 0.38 * speedRatio * speedRatio) * input.forward;
        }
      }

      if (input.brake > 0) {
        if (this.forwardSpeed > 0.6) {
          longAccel -= 38.0 * input.brake;
        } else if (this.forwardSpeed > -12.0) {
          longAccel -= 15.0 * input.brake; // Smooth reverse gear
        }
      }

      if (input.handbrake && Math.abs(this.forwardSpeed) > 1.0) {
        longAccel -= Math.sign(this.forwardSpeed) * 9.5;
      }

      // Apply longitudinal drive impulse through COM (zero nose-lift instability!)
      if (Math.abs(longAccel) > 0.01) {
        const driveImp = chassisForward.clone().multiplyScalar(longAccel * this.mass * gripFactor * dt);
        this.body.applyImpulse({ x: driveImp.x, y: driveImp.y, z: driveImp.z }, true);
      }

      // Lateral tire grip (relaxed during handbrake for buttery controllable arcade drift!)
      const lateralGripRate = input.handbrake ? 5.2 : 13.5;
      const latCorrection = -sideSpeed * Math.min(1.0, lateralGripRate * dt) * this.mass * gripFactor;
      const latImp = chassisRight.clone().multiplyScalar(latCorrection);
      this.body.applyImpulse({ x: latImp.x, y: latImp.y, z: latImp.z }, true);

      // Steering angular velocity around chassisUp
      if (Math.abs(this.forwardSpeed) > 0.35) {
        const dirSign = this.forwardSpeed >= -0.1 ? 1.0 : -1.0;
        const speedTurnFactor = Math.min(1.0, Math.abs(this.forwardSpeed) / 5.5);
        const driftYawBonus = input.handbrake ? 1.28 : 1.0;
        const desiredYawRate = this.currentSteerAngle * 3.85 * speedTurnFactor * dirSign * driftYawBonus;

        const curAng = this.body.angvel();
        const curAngVec = new THREE.Vector3(curAng.x, curAng.y, curAng.z);
        const curYaw = curAngVec.dot(chassisUp);
        const yawDelta = (desiredYawRate - curYaw) * Math.min(1.0, dt * 16.0);
        const newAng = curAngVec.addScaledVector(chassisUp, yawDelta);
        this.body.setAngvel({ x: newAng.x, y: newAng.y, z: newAng.z }, true);
      }

      // LMP Ground-Effect Aerodynamic Downforce (glues car to 3D banked curves & ascending spirals!)
      const aeroDown = -0.34 * this.forwardSpeed * this.forwardSpeed * dt;
      const downImp = chassisUp.clone().multiplyScalar(aeroDown);
      this.body.applyImpulse({ x: downImp.x, y: downImp.y, z: downImp.z }, true);
    } else if (groundedCount === 0) {
      // 3. Mid-Air 3D Ramp Attitude Stabilizer: gently levels roll & limits extreme pitch so jumps land cleanly!
      const worldUp = new THREE.Vector3(0, 1, 0);
      const alignAxis = new THREE.Vector3().crossVectors(chassisUp, worldUp);
      const curAng = this.body.angvel();
      const angVec = new THREE.Vector3(curAng.x, curAng.y, curAng.z);
      angVec.multiplyScalar(Math.max(0, 1.0 - 1.8 * dt));
      angVec.addScaledVector(alignAxis, 3.2 * dt);
      this.body.setAngvel({ x: angVec.x, y: angVec.y, z: angVec.z }, true);
    }

    // 4. Stereo Shield Wall-Glide Boost Preservation: if scraping wall with Shield active, keep speed high!
    this.world.contactPairsWith(this.collider, (otherCol) => {
      if (this.wallHitCooldown <= 0 && Math.abs(this.forwardSpeed) > 6.0) {
        this.wallHitCooldown = 0.18;
        const localHit = new THREE.Vector3(sideSpeed > 0 ? 0.42 : -0.42, 0.22, -0.35);
        if (this.onWallScrape) {
          this.onWallScrape(localHit, Math.min(1, Math.abs(this.forwardSpeed) / 30));
        }
        if (shieldBoostActive && groundedCount > 0 && otherCol.parent() === null) {
          // Smoothly preserve forward momentum along guardrail during Stereo Confidential Shield!
          const boostKeep = chassisForward.clone().multiplyScalar(this.mass * 0.42);
          this.body.applyImpulse({ x: boostKeep.x, y: 0, z: boostKeep.z }, true);
        }
      }
    });

    this.syncVisuals(dt, sideSpeed);
  }

  private syncVisuals(dt: number, sideSpeed: number): void {
    const rbPos = this.body.translation();
    const rbRot = this.body.rotation();
    this.root.position.set(rbPos.x, rbPos.y, rbPos.z);
    this.root.quaternion.set(rbRot.x, rbRot.y, rbRot.z, rbRot.w);

    // Subtle dynamic chassis roll & pitch visual lean
    if (this.chassisVisual) {
      const targetRoll = THREE.MathUtils.clamp(-sideSpeed * 0.012 - this.currentSteerAngle * (this.forwardSpeed * 0.004), -0.06, 0.06);
      this.chassisVisual.rotation.z += (targetRoll - this.chassisVisual.rotation.z) * Math.min(1, dt * 10);
    }

    // Update 4 independent 3D wheels (suspension travel + steering + rolling spin!)
    for (const w of this.wheels) {
      if (!w.mesh) continue;
      w.spinAngle -= (this.forwardSpeed * dt) / w.radius;
      w.mesh.position.y = w.radius + w.compression * 0.65;
      w.mesh.rotation.y = w.isFront ? this.currentSteerAngle : 0;
      w.mesh.rotation.x = w.spinAngle;
    }
  }
}
