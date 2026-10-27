/**
 * Procedural Multi-Oscillator Automotive Engine & Cyber-SFX Synthesizer (Web Audio API).
 * Synthesizes realistic sports-prototype RPM harmonics, 6-speed gear shifts, exhaust crackles,
 * tire drift screech, suspension landing thuds, countdown tones, and "立体密算" shield/boost SFX.
 */
export class EngineAudioSynth {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;

  // Continuous engine nodes
  private oscPrimary: OscillatorNode | null = null;
  private oscSub: OscillatorNode | null = null;
  private oscTurbine: OscillatorNode | null = null;
  private engineFilter: BiquadFilterNode | null = null;
  private engineGain: GainNode | null = null;
  private turbineGain: GainNode | null = null;

  // Tire screech noise loop
  private screechFilter: BiquadFilterNode | null = null;
  private screechGain: GainNode | null = null;

  // Stereo Shield hum loop
  private shieldOsc: OscillatorNode | null = null;
  private shieldGain: GainNode | null = null;

  private isInitialized = false;
  private isMuted = false;

  public currentRpm = 1100;
  public currentGear = 1;
  private shiftCutTimer = 0;

  public init(): void {
    if (this.isInitialized) {
      if (this.ctx && this.ctx.state === 'suspended') {
        this.ctx.resume();
      }
      return;
    }

    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new AudioCtx();

    this.masterGain = this.ctx.createGain();
    this.masterGain.gain.value = 0.42;
    this.masterGain.connect(this.ctx.destination);

    // 1. Engine Harmonic Core (Sawtooth + Sub-Triangle + Soft Waveshaper + Formant Lowpass)
    this.engineFilter = this.ctx.createBiquadFilter();
    this.engineFilter.type = 'lowpass';
    this.engineFilter.frequency.value = 320;
    this.engineFilter.Q.value = 2.6;

    const shaper = this.ctx.createWaveShaper();
    shaper.curve = this.makeSaturationCurve(28);
    shaper.oversample = '2x';

    this.engineGain = this.ctx.createGain();
    this.engineGain.gain.value = 0.0;

    this.oscPrimary = this.ctx.createOscillator();
    this.oscPrimary.type = 'sawtooth';
    this.oscPrimary.frequency.value = 55;

    this.oscSub = this.ctx.createOscillator();
    this.oscSub.type = 'triangle';
    this.oscSub.frequency.value = 27.5;

    const subMix = this.ctx.createGain();
    subMix.gain.value = 0.65;

    this.oscPrimary.connect(shaper);
    this.oscSub.connect(subMix);
    subMix.connect(shaper);
    shaper.connect(this.engineFilter);
    this.engineFilter.connect(this.engineGain);
    this.engineGain.connect(this.masterGain);

    // Hybrid Electric / Turbo Whine
    this.oscTurbine = this.ctx.createOscillator();
    this.oscTurbine.type = 'sine';
    this.oscTurbine.frequency.value = 420;
    this.turbineGain = this.ctx.createGain();
    this.turbineGain.gain.value = 0.0;
    this.oscTurbine.connect(this.turbineGain);
    this.turbineGain.connect(this.masterGain);

    // 2. White-noise buffer for Drift Tire Screech
    const noiseBuf = this.createNoiseBuffer(2.0);
    const noiseSrc = this.ctx.createBufferSource();
    noiseSrc.buffer = noiseBuf;
    noiseSrc.loop = true;

    this.screechFilter = this.ctx.createBiquadFilter();
    this.screechFilter.type = 'bandpass';
    this.screechFilter.frequency.value = 1450;
    this.screechFilter.Q.value = 6.5;

    this.screechGain = this.ctx.createGain();
    this.screechGain.gain.value = 0.0;

    noiseSrc.connect(this.screechFilter);
    this.screechFilter.connect(this.screechGain);
    this.screechGain.connect(this.masterGain);

    // 3. Stereo Confidential Shield Resonance Hum
    this.shieldOsc = this.ctx.createOscillator();
    this.shieldOsc.type = 'triangle';
    this.shieldOsc.frequency.value = 148;
    this.shieldGain = this.ctx.createGain();
    this.shieldGain.gain.value = 0.0;
    this.shieldOsc.connect(this.shieldGain);
    this.shieldGain.connect(this.masterGain);

    this.oscPrimary.start();
    this.oscSub.start();
    this.oscTurbine.start();
    noiseSrc.start();
    this.shieldOsc.start();

    this.isInitialized = true;
  }

  public toggleMute(): boolean {
    this.isMuted = !this.isMuted;
    if (this.masterGain && this.ctx) {
      this.masterGain.gain.setTargetAtTime(this.isMuted ? 0.0 : 0.42, this.ctx.currentTime, 0.04);
    }
    return this.isMuted;
  }

  public get muted(): boolean {
    return this.isMuted;
  }

  public update(
    dt: number,
    speedMps: number,
    throttle: number,
    lateralSlip: number,
    isGrounded: boolean,
    shieldActive: boolean
  ): void {
    // Compute 6-speed gearbox & RPM even if audio not yet unlocked (so HUD tachometer always works!)
    const absSpeed = Math.abs(speedMps);
    const gearTopSpeeds = [7.5, 13.5, 19.8, 26.0, 33.0, 45.0];
    let targetGear = 1;
    for (let g = 0; g < gearTopSpeeds.length; g++) {
      if (absSpeed > gearTopSpeeds[g] * 0.88 && g < gearTopSpeeds.length - 1) {
        targetGear = g + 2;
      }
    }
    if (targetGear !== this.currentGear) {
      if (targetGear > this.currentGear) {
        this.shiftCutTimer = 0.075;
        this.playGearShiftPop();
      }
      this.currentGear = targetGear;
    }

    const gearMin = this.currentGear === 1 ? 0 : gearTopSpeeds[this.currentGear - 2] * 0.62;
    const gearMax = gearTopSpeeds[this.currentGear - 1];
    const gearRatio = Math.max(0, Math.min(1.08, (absSpeed - gearMin) / Math.max(1.0, gearMax - gearMin)));
    const targetRpm = 1150 + gearRatio * 6850 + (throttle > 0.1 && !isGrounded ? 1200 : 0);
    this.currentRpm += (Math.min(8600, targetRpm) - this.currentRpm) * Math.min(1, dt * 14);

    if (this.shiftCutTimer > 0) {
      this.shiftCutTimer -= dt;
    }

    if (!this.isInitialized || !this.ctx || !this.oscPrimary || !this.oscSub || !this.oscTurbine || !this.engineFilter || !this.engineGain || !this.turbineGain || !this.screechGain || !this.screechFilter || !this.shieldGain || !this.shieldOsc) {
      return;
    }

    const now = this.ctx.currentTime;
    const fundHz = (this.currentRpm / 60) * 1.5; // 6-cylinder / V8 order feel
    this.oscPrimary.frequency.setTargetAtTime(fundHz, now, 0.025);
    this.oscSub.frequency.setTargetAtTime(fundHz * 0.5, now, 0.025);
    this.oscTurbine.frequency.setTargetAtTime(240 + this.currentRpm * 0.19 + (shieldActive ? 260 : 0), now, 0.03);

    const load = this.shiftCutTimer > 0 ? 0.15 : (0.35 + 0.65 * Math.abs(throttle));
    this.engineFilter.frequency.setTargetAtTime(220 + (this.currentRpm / 8500) * 1950 * load, now, 0.03);
    this.engineGain.gain.setTargetAtTime(0.14 + 0.18 * load, now, 0.03);
    this.turbineGain.gain.setTargetAtTime(shieldActive ? 0.085 : 0.022 * (this.currentRpm / 8500), now, 0.04);

    // Drift tire screech
    const slipIntensity = isGrounded && absSpeed > 4.0 ? Math.max(0, Math.min(1, (lateralSlip - 0.18) * 1.8)) : 0;
    this.screechFilter.frequency.setTargetAtTime(1250 + slipIntensity * 620, now, 0.04);
    this.screechGain.gain.setTargetAtTime(slipIntensity * 0.16, now, 0.04);

    // Stereo Shield hum
    this.shieldOsc.frequency.setTargetAtTime(140 + Math.sin(now * 8.0) * 12 + absSpeed * 2.2, now, 0.05);
    this.shieldGain.gain.setTargetAtTime(shieldActive ? 0.09 : 0.0, now, 0.06);
  }

  public playCountdownTone(isGo: boolean): void {
    if (!this.isInitialized || !this.ctx || !this.masterGain) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = isGo ? 'triangle' : 'sine';
    osc.frequency.setValueAtTime(isGo ? 880 : 440, now);
    if (isGo) {
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.28);
    }
    g.gain.setValueAtTime(0.28, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + (isGo ? 0.48 : 0.22));
    osc.connect(g);
    g.connect(this.masterGain);
    osc.start(now);
    osc.stop(now + (isGo ? 0.50 : 0.24));
  }

  public playCryptoPickup(): void {
    if (!this.isInitialized || !this.ctx || !this.masterGain) return;
    const now = this.ctx.currentTime;
    const notes = [660, 990, 1320];
    notes.forEach((freq, i) => {
      if (!this.ctx || !this.masterGain) return;
      const osc = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, now + i * 0.045);
      g.gain.setValueAtTime(0.18, now + i * 0.045);
      g.gain.exponentialRampToValueAtTime(0.001, now + i * 0.045 + 0.18);
      osc.connect(g);
      g.connect(this.masterGain);
      osc.start(now + i * 0.045);
      osc.stop(now + i * 0.045 + 0.20);
    });
  }

  public playShieldActivate(): void {
    if (!this.isInitialized || !this.ctx || !this.masterGain) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(180, now);
    osc.frequency.exponentialRampToValueAtTime(920, now + 0.35);

    const flt = this.ctx.createBiquadFilter();
    flt.type = 'bandpass';
    flt.frequency.setValueAtTime(600, now);
    flt.frequency.exponentialRampToValueAtTime(2200, now + 0.35);
    flt.Q.value = 3.0;

    g.gain.setValueAtTime(0.32, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    osc.connect(flt);
    flt.connect(g);
    g.connect(this.masterGain);
    osc.start(now);
    osc.stop(now + 0.46);
  }

  public playImpact(intensity = 0.6, shielded = false): void {
    if (!this.isInitialized || !this.ctx || !this.masterGain) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = shielded ? 'sine' : 'triangle';
    osc.frequency.setValueAtTime(shielded ? 520 : 135, now);
    osc.frequency.exponentialRampToValueAtTime(shielded ? 140 : 38, now + 0.18);
    g.gain.setValueAtTime(Math.min(0.38, 0.12 + intensity * 0.25), now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.20);
    osc.connect(g);
    g.connect(this.masterGain);
    osc.start(now);
    osc.stop(now + 0.22);
  }

  private playGearShiftPop(): void {
    if (!this.isInitialized || !this.ctx || !this.masterGain) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(150, now);
    osc.frequency.exponentialRampToValueAtTime(48, now + 0.07);
    g.gain.setValueAtTime(0.14, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.075);
    osc.connect(g);
    g.connect(this.masterGain);
    osc.start(now);
    osc.stop(now + 0.08);
  }

  private makeSaturationCurve(amount: number): Float32Array<ArrayBuffer> {
    const n = 512;
    const curve = new Float32Array(new ArrayBuffer(n * 4));
    for (let i = 0; i < n; i++) {
      const x = (i * 2) / n - 1;
      curve[i] = ((3 + amount) * x * 20 * (Math.PI / 180)) / (Math.PI + amount * Math.abs(x));
    }
    return curve;
  }

  private createNoiseBuffer(durationSec: number): AudioBuffer {
    const ctx = this.ctx!;
    const length = Math.floor(ctx.sampleRate * durationSec);
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) {
      data[i] = Math.random() * 2 - 1;
    }
    return buffer;
  }
}
