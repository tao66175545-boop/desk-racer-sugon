import * as THREE from 'three';
import { CameraMode, RacePhase, TrackMetadata } from '../types';

export function formatRaceTime(ms: number): string {
  const clamped = Math.max(0, Math.floor(ms));
  const minutes = Math.floor(clamped / 60000);
  const seconds = Math.floor((clamped % 60000) / 1000);
  const centis = Math.floor((clamped % 1000) / 10);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(centis).padStart(2, '0')}`;
}

export class HUD {
  private loadingScreen = document.getElementById('loading-screen')!;
  private loadingBar = document.getElementById('loading-bar')!;
  private loadingStatus = document.getElementById('loading-status')!;

  private introOverlay = document.getElementById('intro-overlay')!;
  private hudLayer = document.getElementById('hud-layer')!;
  private finishOverlay = document.getElementById('finish-overlay')!;

  private elLap = document.getElementById('hud-lap')!;
  private elCamBadge = document.getElementById('hud-cam-badge')!;
  private elCurTime = document.getElementById('hud-cur-time')!;
  private elBestTime = document.getElementById('hud-best-time')!;

  private elCountdown = document.getElementById('hud-countdown')!;
  private elToast = document.getElementById('hud-toast')!;
  private elWrongWay = document.getElementById('hud-wrong-way')!;
  private elRefPip = document.getElementById('ref-pip')!;

  private elShieldPct = document.getElementById('hud-shield-pct')!;
  private elShieldHint = document.getElementById('hud-shield-hint')!;
  private layerSegs: HTMLElement[];

  private elGear = document.getElementById('hud-gear')!;
  private elSpeed = document.getElementById('hud-speed')!;
  private elRpmFill = document.getElementById('hud-rpm-fill')!;
  private pillAir = document.getElementById('pill-air')!;
  private pillDrift = document.getElementById('pill-drift')!;
  private pillShield = document.getElementById('pill-shield')!;

  private minimapCanvas = document.getElementById('minimap-canvas') as HTMLCanvasElement;
  private minimapCtx: CanvasRenderingContext2D;

  private meta: TrackMetadata | null = null;
  private toastTimer = 0;
  private goBannerTimer = 0;

  constructor(
    onStartRace: () => void,
    onRestartRace: () => void,
    onToggleMute: () => boolean
  ) {
    this.minimapCtx = this.minimapCanvas.getContext('2d')!;
    this.layerSegs = Array.from(document.querySelectorAll('#hud-five-layers .layer-seg'));

    document.getElementById('btn-start-race')!.addEventListener('click', () => {
      this.introOverlay.classList.add('hidden');
      this.hudLayer.classList.remove('hidden');
      onStartRace();
    });

    document.getElementById('btn-restart-race')!.addEventListener('click', () => {
      this.finishOverlay.classList.add('hidden');
      this.hudLayer.classList.remove('hidden');
      onRestartRace();
    });

    const muteBtn = document.getElementById('btn-mute')!;
    muteBtn.addEventListener('click', () => {
      const muted = onToggleMute();
      muteBtn.textContent = muted ? '🔇' : '🔊';
    });
  }

  public setLoadingProgress(pct: number, statusText?: string): void {
    this.loadingBar.style.width = `${Math.min(100, Math.max(5, pct))}%`;
    if (statusText) {
      this.loadingStatus.textContent = statusText;
    }
  }

  public showIntro(meta: TrackMetadata): void {
    this.meta = meta;
    this.loadingScreen.classList.add('hidden');
    this.introOverlay.classList.remove('hidden');
  }

  public toggleRefPip(): void {
    this.elRefPip.classList.toggle('hidden');
  }

  public updateMuteIcon(muted: boolean): void {
    document.getElementById('btn-mute')!.textContent = muted ? '🔇' : '🔊';
  }

  public setCameraBadge(mode: CameraMode): void {
    const labels: Record<CameraMode, string> = {
      chase: 'CHASE 追尾视角',
      hood: 'HOOD 引擎盖视角',
      overview: 'DESK 桌面全景',
    };
    this.elCamBadge.textContent = labels[mode];
  }

  public showToast(msg: string, duration = 2.4): void {
    this.elToast.textContent = msg;
    this.elToast.classList.remove('hidden');
    this.toastTimer = duration;
  }

  public triggerGoBanner(): void {
    this.goBannerTimer = 0.85;
  }

  public showFinishSummary(totalMs: number, bestMs: number, lapHistoryMs: number[]): void {
    this.hudLayer.classList.add('hidden');
    this.finishOverlay.classList.remove('hidden');
    document.getElementById('fin-total-time')!.textContent = formatRaceTime(totalMs);
    document.getElementById('fin-best-time')!.textContent = formatRaceTime(bestMs);

    const listEl = document.getElementById('fin-lap-list')!;
    listEl.innerHTML = '';
    lapHistoryMs.forEach((ms, idx) => {
      const row = document.createElement('div');
      row.className = 'lap-breakdown-row';
      const isBest = Math.abs(ms - bestMs) < 5;
      row.innerHTML = `<span>第 ${idx + 1} 圈 (LAP ${idx + 1})</span><strong style="color:${isBest ? '#00f0ff' : '#fff'}">${formatRaceTime(ms)}${isBest ? ' ★ BEST' : ''}</strong>`;
      listEl.appendChild(row);
    });
  }

  public update(
    dt: number,
    phase: RacePhase,
    countdownVal: number,
    lap: number,
    totalLaps: number,
    curLapMs: number,
    bestLapMs: number | null,
    wrongWay: boolean,
    speedMps: number,
    rpm: number,
    gear: number,
    groundedWheels: number,
    isDrifting: boolean,
    shieldEnergy: number,
    shieldActive: boolean,
    carPos: THREE.Vector3,
    carForward: THREE.Vector3
  ): void {
    if (this.toastTimer > 0) {
      this.toastTimer -= dt;
      if (this.toastTimer <= 0) {
        this.elToast.classList.add('hidden');
      }
    }

    if (this.goBannerTimer > 0) {
      this.goBannerTimer -= dt;
    }

    // Countdown center overlay
    if (phase === 'countdown' && countdownVal > 0) {
      this.elCountdown.textContent = String(countdownVal);
      this.elCountdown.classList.remove('hidden');
    } else if (this.goBannerTimer > 0) {
      this.elCountdown.textContent = 'GO!';
      this.elCountdown.classList.remove('hidden');
    } else {
      this.elCountdown.classList.add('hidden');
    }

    // Lap & timers
    this.elLap.textContent = `${lap} / ${totalLaps}`;
    this.elCurTime.textContent = formatRaceTime(curLapMs);
    this.elBestTime.textContent = bestLapMs !== null ? formatRaceTime(bestLapMs) : '--:--.--';

    // Wrong way
    this.elWrongWay.classList.toggle('hidden', !wrongWay);

    // Speedometer (1:10 miniature scale factor -> exhilarating realistic hypercar km/h display!)
    const displayKmh = Math.round(Math.abs(speedMps) * 7.2);
    this.elSpeed.textContent = String(displayKmh);
    this.elGear.textContent = speedMps < -0.8 ? 'R' : String(gear);

    const rpmPct = Math.min(100, Math.max(8, ((rpm - 1000) / 7500) * 100));
    this.elRpmFill.style.width = `${rpmPct}%`;

    this.pillAir.classList.toggle('hidden', groundedWheels > 0 || phase !== 'racing');
    this.pillDrift.classList.toggle('hidden', !isDrifting || groundedWheels === 0);
    this.pillShield.classList.toggle('hidden', !shieldActive);

    // 5-Layer Stereo Confidential Computing Gauge
    const pctRound = Math.round(shieldEnergy);
    this.elShieldPct.textContent = `${pctRound}%`;
    const activeLayers = Math.floor(shieldEnergy / 20);
    this.layerSegs.forEach((seg, idx) => {
      seg.classList.toggle('charged', !shieldActive && idx < activeLayers);
      seg.classList.toggle('overdrive', shieldActive && shieldEnergy > idx * 20);
    });

    if (shieldActive) {
      this.elShieldHint.textContent = '⚡ 立体密算全息护盾激活中：免除撞墙减速 + 电磁震飞障碍 +45% 极速';
      this.elShieldHint.classList.add('ready');
    } else if (shieldEnergy >= 20) {
      this.elShieldHint.textContent = '就绪！按 [Shift / E] 开启【立体密算】六边形密态护盾超频冲刺';
      this.elShieldHint.classList.add('ready');
    } else {
      this.elShieldHint.textContent = '拾取赛道【密态算力块】或手刹漂移充能...';
      this.elShieldHint.classList.remove('ready');
    }

    this.drawMinimap(carPos, carForward);
  }

  private drawMinimap(carPos: THREE.Vector3, carForward: THREE.Vector3): void {
    if (!this.meta) return;
    const ctx = this.minimapCtx;
    const w = this.minimapCanvas.width;
    const h = this.minimapCanvas.height;
    ctx.clearRect(0, 0, w, h);

    // Map Three.js X in [-13.5, +13.5], Z in [-7.5, +7.5] into 210x136 canvas
    const toX = (x: number) => ((x + 13.5) / 27.0) * (w - 20) + 10;
    const toY = (z: number) => ((z + 7.5) / 15.0) * (h - 20) + 10;

    // Desk outline
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.14)';
    ctx.lineWidth = 1;
    ctx.strokeRect(8, 8, w - 16, h - 16);

    const wps = this.meta.waypoints;
    ctx.lineCap = 'round';
    for (let i = 0; i < wps.length; i++) {
      const p0 = wps[i];
      const p1 = wps[(i + 1) % wps.length];
      ctx.beginPath();
      ctx.moveTo(toX(p0.pos[0]), toY(p0.pos[2]));
      ctx.lineTo(toX(p1.pos[0]), toY(p1.pos[2]));
      ctx.lineWidth = 4.2;
      // Elevation > 0.65m = Elevated Ramp / Overpass in Sugon Red; Ground = Cyan!
      ctx.strokeStyle = p0.pos[1] > 0.65 ? '#ff2442' : 'rgba(0, 240, 255, 0.72)';
      ctx.stroke();
    }

    // Start/Finish Gantry tick
    const sg = this.meta.startGantry.pos;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(toX(sg[0]) - 2, toY(sg[2]) - 6, 4, 12);

    // Player Car directional pointer
    const px = toX(carPos.x);
    const py = toY(carPos.z);
    const ang = Math.atan2(carForward.z, carForward.x);

    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(ang);
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = '#00f0ff';
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.moveTo(7, 0);
    ctx.lineTo(-5, -4.5);
    ctx.lineTo(-5, 4.5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
}
