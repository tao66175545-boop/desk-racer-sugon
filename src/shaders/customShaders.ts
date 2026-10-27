import * as THREE from 'three';

/**
 * 1. Custom GLSL Flowing Cyber-Neon Track Guardrail Shader
 * Animates directional energy pulses along circuit UV.x, reactive to car speed and Stereo Shield boost.
 */
export function createNeonRailMaterial(isRedSide: boolean): THREE.ShaderMaterial {
  const primary = isRedSide ? new THREE.Color(0xff1432) : new THREE.Color(0x00f0ff);
  const secondary = isRedSide ? new THREE.Color(0xff7b00) : new THREE.Color(0x2878ff);

  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uBoostFactor: { value: 0 },
      uColorPrimary: { value: primary },
      uColorSecondary: { value: secondary },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      varying vec3 vNormalView;
      varying vec3 vViewPos;

      void main() {
        vUv = uv;
        vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
        vViewPos = -mvPos.xyz;
        vNormalView = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uBoostFactor;
      uniform vec3 uColorPrimary;
      uniform vec3 uColorSecondary;

      varying vec2 vUv;
      varying vec3 vNormalView;
      varying vec3 vViewPos;

      void main() {
        float flowSpeed = 1.6 + uBoostFactor * 3.2;
        float wave1 = sin(vUv.x * 90.0 - uTime * flowSpeed * 6.0) * 0.5 + 0.5;
        float wave2 = sin(vUv.x * 24.0 - uTime * flowSpeed * 2.2) * 0.5 + 0.5;
        float pulsePacket = pow(wave1, 4.0) * 0.85 + pow(wave2, 3.0) * 0.55;

        vec3 V = normalize(vViewPos);
        vec3 N = normalize(vNormalView);
        float coreDot = clamp(abs(dot(V, N)), 0.0, 1.0);

        vec3 baseCol = mix(uColorSecondary, uColorPrimary, 0.55 + 0.45 * wave2);
        vec3 hotCore = vec3(1.0, 0.98, 1.0) * pow(coreDot, 2.8) * (0.28 + 0.42 * pulsePacket);

        float intensity = 0.92 + pulsePacket * 0.72 + uBoostFactor * 0.55;
        vec3 finalCol = baseCol * intensity + hotCore;

        gl_FragColor = vec4(finalCol, 1.0);
      }
    `,
  });
}

/**
 * 2. Custom GLSL "立体密算 (Stereo Confidential Computing)" 5-Layer Holographic Hex Shield Shader
 * Features:
 *  - Procedural hexagonal geodesic forcefield lattice
 *  - 5 vertical scanning confidential architecture rings (L1..L5)
 *  - Scrolling cipher data matrix shimmer
 *  - Fresnel rim energy + collision shockwave ripple (`uHitPos`, `uHitAge`)
 */
export function createStereoShieldMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uStrength: { value: 0 },
      uHitLocalPos: { value: new THREE.Vector3(0, 0, -1) },
      uHitAge: { value: 10.0 },
    },
    vertexShader: /* glsl */ `
      uniform float uTime;
      uniform float uStrength;
      uniform vec3 uHitLocalPos;
      uniform float uHitAge;

      varying vec3 vLocalPos;
      varying vec3 vNormalView;
      varying vec3 vViewDir;

      void main() {
        vLocalPos = position;
        float breathe = sin(uTime * 7.0 + position.z * 5.0) * 0.012 * uStrength;

        // Subtle shockwave displacement on impact
        float distHit = distance(position, uHitLocalPos);
        float ripple = 0.0;
        if (uHitAge < 1.2) {
          float waveFront = uHitAge * 2.6;
          ripple = exp(-pow((distHit - waveFront) * 6.0, 2.0)) * (1.0 - uHitAge / 1.2) * 0.045;
        }

        vec3 displaced = position + normal * (breathe + ripple);
        vec4 mvPos = modelViewMatrix * vec4(displaced, 1.0);
        vViewDir = normalize(-mvPos.xyz);
        vNormalView = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uStrength;
      uniform vec3 uHitLocalPos;
      uniform float uHitAge;

      varying vec3 vLocalPos;
      varying vec3 vNormalView;
      varying vec3 vViewDir;

      // Procedural hexagonal grid distance to edge
      float hexEdgeDist(vec2 p) {
        const vec2 s = vec2(1.0, 1.7320508);
        vec4 hC = floor(vec4(p, p - vec2(0.5, 1.0)) / s.xyxy) + 0.5;
        vec4 h = vec4(p - hC.xy * s, p - (hC.zw + 0.5) * s);
        vec2 nearest = (dot(h.xy, h.xy) < dot(h.zw, h.zw)) ? h.xy : h.zw;
        nearest = abs(nearest);
        float d = max(dot(nearest, s * 0.5), nearest.x);
        return abs(0.5 - d);
      }

      float hash21(vec2 p) {
        p = fract(p * vec2(123.34, 456.21));
        p += dot(p, p + 45.32);
        return fract(p.x * p.y);
      }

      void main() {
        if (uStrength <= 0.005) discard;

        vec3 N = normalize(vNormalView);
        vec3 V = normalize(vViewDir);
        float fresnel = pow(1.0 - clamp(abs(dot(N, V)), 0.0, 1.0), 2.3);

        // Tri-planar / cylindrical hex projection around aerodynamic shell
        vec2 hexUv = vec2(atan(vLocalPos.x, vLocalPos.y + 0.25) * 3.2, vLocalPos.z * 7.5 - uTime * 2.4);
        float hDist = hexEdgeDist(hexUv);
        float hexLine = smoothstep(0.085, 0.015, hDist);

        // Encrypted cipher cell flicker inside hex cells
        vec2 cellId = floor(hexUv * 2.0 + vec2(0.0, floor(uTime * 8.0)));
        float cipherSpark = step(0.86, hash21(cellId)) * (0.5 + 0.5 * sin(uTime * 20.0 + cellId.x));

        // 5-Layer Stereo Confidential Computing scan bands along Y/Z
        float fiveLayerScan = pow(0.5 + 0.5 * sin(vLocalPos.y * 28.0 - uTime * 9.0 + vLocalPos.z * 6.0), 6.0);

        // Impact shockwave ring
        float distHit = distance(vLocalPos, uHitLocalPos);
        float hitGlow = 0.0;
        if (uHitAge < 1.2) {
          float waveFront = uHitAge * 2.6;
          hitGlow = exp(-pow((distHit - waveFront) * 5.5, 2.0)) * (1.0 - uHitAge / 1.2) * 2.5;
        }

        vec3 colCyan = vec3(0.0, 0.95, 1.0);
        vec3 colTrustedBlue = vec3(0.10, 0.45, 1.0);
        vec3 colSugonRed = vec3(1.0, 0.12, 0.26);

        vec3 col = mix(colTrustedBlue, colCyan, fresnel * 0.8 + hexLine * 0.5);
        col = mix(col, colSugonRed, fiveLayerScan * 0.42 + hitGlow * 0.65);
        col += vec3(0.8, 0.98, 1.0) * (cipherSpark * 0.55 + hitGlow * 0.9);

        float alpha = clamp(
          (fresnel * 0.72 + hexLine * 0.45 + fiveLayerScan * 0.28 + cipherSpark * 0.22 + hitGlow) * uStrength,
          0.0,
          0.92
        );

        gl_FragColor = vec4(col * (1.5 + hitGlow), alpha);
      }
    `,
  });
}

/**
 * 3. Custom GLSL Start/Finish Sugon Cloud Holographic Laser Curtain Shader
 */
export function createGantryHoloMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uLapFlash: { value: 0 },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      uniform float uLapFlash;
      varying vec2 vUv;

      void main() {
        float scan = sin(vUv.y * 95.0 - uTime * 12.0) * 0.5 + 0.5;
        float chevron = sin(abs(vUv.x - 0.5) * 36.0 - vUv.y * 10.0 - uTime * 5.5) * 0.5 + 0.5;
        float chevronBand = smoothstep(0.68, 0.95, chevron);

        // Fade smoothly toward bottom so cars pass through a laser mist
        float vertMask = smoothstep(0.0, 0.35, vUv.y) * smoothstep(1.0, 0.82, vUv.y);
        float edgeGlow = smoothstep(0.08, 0.0, abs(vUv.y - 0.92)) + smoothstep(0.05, 0.0, abs(vUv.x - 0.02)) + smoothstep(0.05, 0.0, abs(vUv.x - 0.98));

        vec3 cyan = vec3(0.0, 0.90, 1.0);
        vec3 red = vec3(1.0, 0.10, 0.22);
        vec3 col = mix(cyan, red, smoothstep(0.3, 0.8, abs(vUv.x - 0.5) * 2.0));
        col += vec3(0.9, 1.0, 1.0) * (chevronBand * 0.55 + uLapFlash * 1.8);

        float alpha = clamp((0.14 + scan * 0.12 + chevronBand * 0.24) * vertMask + edgeGlow * 0.45 + uLapFlash * 0.55, 0.0, 0.85);
        gl_FragColor = vec4(col * 1.35, alpha);
      }
    `,
  });
}

/**
 * 4. Custom GLSL Directional Chevron Speed-Boost Pad Shader
 */
export function createBoostPadMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uTime;
      varying vec2 vUv;

      void main() {
        // vUv.y = 0 (back) -> 1 (forward along -Z)
        float cx = abs(vUv.x - 0.5) * 2.0;
        float arrowPhase = fract(vUv.y * 3.0 - cx * 0.65 - uTime * 2.8);
        float arrow = smoothstep(0.18, 0.42, arrowPhase) * smoothstep(0.72, 0.48, arrowPhase);
        float border = smoothstep(0.88, 0.98, cx) * smoothstep(1.0, 0.96, cx);

        float fadeEnds = smoothstep(0.0, 0.12, vUv.y) * smoothstep(1.0, 0.88, vUv.y);
        vec3 col = mix(vec3(0.0, 0.92, 1.0), vec3(1.0, 0.16, 0.28), cx * 0.75);
        float alpha = (arrow * 0.78 + border * 0.65) * fadeEnds;
        if (alpha < 0.02) discard;
        gl_FragColor = vec4(col * 1.9, alpha);
      }
    `,
  });
}
