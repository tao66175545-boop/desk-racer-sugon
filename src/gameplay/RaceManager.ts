import * as THREE from 'three';
import { CheckpointData, PoseData, RacePhase, TrackMetadata } from '../types';

const BEST_LAP_STORAGE_KEY = 'desk_racer_sugon_best_lap_ms';

export class RaceManager {
  public phase: RacePhase = 'intro';
  public readonly totalLaps = 3;
  public currentLap = 1;
  public nextCheckpointIdx = 0; // First cross Gantry (0) to start Lap 1 clock, or spawn just behind 0!

  public countdownValue = 3;
  private countdownTimer = 0;
  private lastCountdownBeep = -1;

  public currentLapMs = 0;
  public totalRaceMs = 0;
  public bestLapMs: number | null = null;
  public lapHistoryMs: number[] = [];
  public isWrongWay = false;
  public lapFlash = 0;

  private checkpoints: CheckpointData[];
  private startSpawn: PoseData;
  private gantryLightMats: THREE.MeshStandardMaterial[] = [];

  public onCountdownBeep: ((isGo: boolean) => void) | null = null;
  public onLapCompleted: ((lapNum: number, lapMs: number, isBest: boolean) => void) | null = null;
  public onRaceFinished: ((totalMs: number, bestMs: number) => void) | null = null;

  constructor(meta: TrackMetadata, gantryRoot: THREE.Object3D) {
    this.checkpoints = meta.checkpoints;
    this.startSpawn = meta.carSpawn;

    const saved = localStorage.getItem(BEST_LAP_STORAGE_KEY);
    if (saved) {
      const parsed = Number(saved);
      if (Number.isFinite(parsed) && parsed > 3000) {
        this.bestLapMs = parsed;
      }
    }

    // Bind 5 F1 Starting Light Lenses on Start Gantry
    for (let i = 0; i < 5; i++) {
      const node = gantryRoot.getObjectByName(`Gantry_StartLight_${i}`);
      if (node && (node as THREE.Mesh).isMesh) {
        const mesh = node as THREE.Mesh;
        const stdMat = new THREE.MeshStandardMaterial({
          color: 0x22080c,
          emissive: 0x000000,
          emissiveIntensity: 0.0,
          roughness: 0.2,
        });
        mesh.material = stdMat;
        this.gantryLightMats.push(stdMat);
      }
    }
  }

  public startCountdown(): void {
    this.phase = 'countdown';
    this.currentLap = 1;
    this.nextCheckpointIdx = 1; // Car spawns right behind Gantry, crosses CP0 immediately into CP1..9 -> CP0
    this.currentLapMs = 0;
    this.totalRaceMs = 0;
    this.lapHistoryMs = [];
    this.countdownTimer = 3.2;
    this.lastCountdownBeep = 4;
    this.setGantryLights(0, false);
  }

  public getRespawnPose(): PoseData {
    if (this.phase === 'countdown' || this.phase === 'intro') {
      return this.startSpawn;
    }
    const lastClearedIdx = (this.nextCheckpointIdx - 1 + this.checkpoints.length) % this.checkpoints.length;
    const cp = this.checkpoints[lastClearedIdx];
    return {
      pos: [cp.pos[0] + cp.up[0] * 0.30, cp.pos[1] + cp.up[1] * 0.30, cp.pos[2] + cp.up[2] * 0.30],
      tangent: cp.tangent,
      up: cp.up,
    };
  }

  public update(dt: number, carPos: THREE.Vector3, carForward: THREE.Vector3, speedMps: number): void {
    if (this.lapFlash > 0) {
      this.lapFlash = Math.max(0, this.lapFlash - dt * 2.2);
    }

    if (this.phase === 'countdown') {
      this.countdownTimer -= dt;
      const secLeft = Math.ceil(this.countdownTimer);
      this.countdownValue = Math.max(0, secLeft);

      // Illuminate 5 gantry pods progressively (1..5 red, then all green on GO!)
      const podsLit = Math.min(5, Math.max(1, Math.floor((3.2 - this.countdownTimer) / 0.58) + 1));
      if (this.countdownTimer > 0) {
        this.setGantryLights(podsLit, false);
        if (secLeft < this.lastCountdownBeep && secLeft >= 1) {
          this.lastCountdownBeep = secLeft;
          if (this.onCountdownBeep) this.onCountdownBeep(false);
        }
      } else {
        this.phase = 'racing';
        this.setGantryLights(5, true);
        if (this.onCountdownBeep) this.onCountdownBeep(true);
      }
      return;
    }

    if (this.phase !== 'racing') return;

    const dtMs = dt * 1000;
    this.currentLapMs += dtMs;
    this.totalRaceMs += dtMs;

    // Check 3D Checkpoint Crossing (3D sphere + vertical separation protects Underpass vs Overpass!)
    const targetCp = this.checkpoints[this.nextCheckpointIdx];
    const cpPos = new THREE.Vector3(...targetCp.pos);
    const dy = Math.abs(carPos.y - cpPos.y);
    const distSq = carPos.distanceToSquared(cpPos);

    if (dy < 1.25 && distSq < 3.85 * 3.85) {
      if (this.nextCheckpointIdx === 0) {
        // Completed a full lap across Sugon Cloud Start/Finish Gantry!
        const finishedLapMs = this.currentLapMs;
        this.lapHistoryMs.push(finishedLapMs);
        this.lapFlash = 1.0;

        let isNewBest = false;
        if (this.bestLapMs === null || finishedLapMs < this.bestLapMs) {
          this.bestLapMs = finishedLapMs;
          isNewBest = true;
          localStorage.setItem(BEST_LAP_STORAGE_KEY, String(Math.round(finishedLapMs)));
        }

        if (this.onLapCompleted) {
          this.onLapCompleted(this.currentLap, finishedLapMs, isNewBest);
        }

        if (this.currentLap >= this.totalLaps) {
          this.phase = 'finished';
          if (this.onRaceFinished) {
            this.onRaceFinished(this.totalRaceMs, this.bestLapMs!);
          }
          return;
        }

        this.currentLap++;
        this.currentLapMs = 0;
        this.nextCheckpointIdx = 1;
      } else {
        this.nextCheckpointIdx = (this.nextCheckpointIdx + 1) % this.checkpoints.length;
      }
    }

    // Wrong-way detection against nearest 3D checkpoint tangent
    let nearestCp = this.checkpoints[0];
    let minD = Infinity;
    for (const cp of this.checkpoints) {
      const p = new THREE.Vector3(...cp.pos);
      const d = carPos.distanceToSquared(p) + Math.pow(carPos.y - p.y, 2) * 4.0;
      if (d < minD) {
        minD = d;
        nearestCp = cp;
      }
    }
    const refTan = new THREE.Vector3(...nearestCp.tangent);
    this.isWrongWay = speedMps > 3.5 && carForward.dot(refTan) < -0.45;
  }

  private setGantryLights(count: number, isGreenGo: boolean): void {
    for (let i = 0; i < this.gantryLightMats.length; i++) {
      const mat = this.gantryLightMats[i];
      if (isGreenGo) {
        mat.color.setHex(0x00ff88);
        mat.emissive.setHex(0x00ff77);
        mat.emissiveIntensity = 4.2;
      } else if (i < count) {
        mat.color.setHex(0xff1428);
        mat.emissive.setHex(0xff0820);
        mat.emissiveIntensity = 4.5;
      } else {
        mat.color.setHex(0x1f080c);
        mat.emissive.setHex(0x000000);
        mat.emissiveIntensity = 0.0;
      }
    }
  }
}
