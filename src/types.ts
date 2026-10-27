export interface Vec3Tuple {
  0: number;
  1: number;
  2: number;
}

export interface TrackWaypoint {
  pos: [number, number, number];
  tangent: [number, number, number];
  right: [number, number, number];
  up: [number, number, number];
  bankDeg: number;
  s: number;
}

export interface CheckpointData {
  id: number;
  pos: [number, number, number];
  tangent: [number, number, number];
  up: [number, number, number];
  right: [number, number, number];
  width: number;
  s: number;
}

export interface BoostPadData {
  id: number;
  pos: [number, number, number];
  tangent: [number, number, number];
  up: [number, number, number];
  right: [number, number, number];
}

export interface CryptoNodeData {
  id: number;
  pos: [number, number, number];
  up: [number, number, number];
}

export interface DynamicPropData {
  id: number;
  kind: 'keycap_red' | 'keycap_cyan' | 'dice' | 'eraser' | 'energy_can';
  pos: [number, number, number];
}

export interface PoseData {
  pos: [number, number, number];
  tangent: [number, number, number];
  up: [number, number, number];
  right?: [number, number, number];
}

export interface TrackMetadata {
  totalLength: number;
  trackWidth: number;
  startGantry: Required<PoseData>;
  carSpawn: PoseData;
  checkpoints: CheckpointData[];
  boostPads: BoostPadData[];
  cryptoNodes: CryptoNodeData[];
  dynamicProps: DynamicPropData[];
  waypoints: TrackWaypoint[];
}

export type CameraMode = 'chase' | 'hood' | 'overview';

export type RacePhase = 'intro' | 'countdown' | 'racing' | 'finished';
