import { useState, useEffect } from 'react';
import type { SujonState } from '../store/sessionCockpitStore';

export type { SujonState };
export const AGENT_STATE_EVENT = 'supremeai:agent-state';
export const SUJON_STATE_EVENT = 'supremeai:sujon-state';

export function setAgentState(state: SujonState): void {
  window.dispatchEvent(new CustomEvent<SujonState>(AGENT_STATE_EVENT, { detail: state }));
  window.dispatchEvent(new CustomEvent<SujonState>(SUJON_STATE_EVENT, { detail: state }));
}

export function useAgentState(): SujonState {
  const [state, setState] = useState<SujonState>('idle');
  useEffect(() => {
    const onState = (e: Event) => setState((e as CustomEvent<SujonState>).detail);
    window.addEventListener(AGENT_STATE_EVENT, onState);
    window.addEventListener(SUJON_STATE_EVENT, onState);
    return () => {
      window.removeEventListener(AGENT_STATE_EVENT, onState);
      window.removeEventListener(SUJON_STATE_EVENT, onState);
    };
  }, []);
  return state;
}

// Shader sources
export const vertexShaderSource = `#version 300 es
precision highp float;
in vec2 a_position;
in vec2 a_texCoord;
out vec2 v_texCoord;
void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
    v_texCoord = a_texCoord;
}
`;

export const fragmentShaderSource = `#version 300 es
precision highp float;
in vec2 v_texCoord;
out vec4 outColor;
uniform float u_time;
uniform vec2 u_resolution;
uniform vec3 u_baseColor;
uniform float u_intensity;
uniform int u_stateId;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;
    vec2 pos = (uv - 0.5) * 2.0;
    pos.x *= u_resolution.x / u_resolution.y;

    vec3 color = u_baseColor;
    float n = 0.0;

    if (u_stateId == 0) { // Idle
        n = noise(pos * 3.0 + u_time * 0.2) * 0.5;
        color *= (0.5 + n);
    } else if (u_stateId == 1) { // Scanning
        float scan = sin(uv.y * 50.0 + u_time * 5.0) * 0.5 + 0.5;
        float sweep = step(0.9, fract(uv.x * 2.0 - u_time));
        color *= (0.5 + scan * 0.5 + sweep * u_intensity);
    } else if (u_stateId == 2) { // Executing / Processing
        n = noise(vec2(pos.x * 10.0 - u_time * 5.0, pos.y * 2.0));
        color *= step(0.6, n) * 1.5;
    } else if (u_stateId == 3) { // Self-Healing
        n = noise(pos * 5.0 + floor(u_time * 10.0) * 0.1);
        color *= (0.5 + n);
    } else if (u_stateId == 4) { // CircuitOpen
        float dist = length(pos);
        float vignette = smoothstep(1.5, 0.5, dist);
        float pulse = sin(u_time * 2.0) * 0.2 + 0.8;
        color *= vignette * pulse;
    } else if (u_stateId == 5) { // AwaitingHuman
        float dist = length(pos);
        float pulse = sin(u_time * 3.0 - dist * 5.0) * 0.5 + 0.5;
        color *= (0.5 + pulse * 0.5);
    } else if (u_stateId == 6) { // Success
        float wave = sin(u_time * 10.0 - length(pos) * 10.0);
        color *= smoothstep(0.0, 1.0, wave);
    } else if (u_stateId == 7) { // Failed
        float wave = sin(length(pos) * 20.0 + u_time * 10.0);
        color *= smoothstep(0.0, 1.0, wave);
    }

    outColor = vec4(color, 0.3); // Kept subtle
}
`;

// Helper functions
export function createShader(gl: WebGL2RenderingContext, type: number, source: string) {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error(gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

export function createProgram(gl: WebGL2RenderingContext, vertexShader: WebGLShader, fragmentShader: WebGLShader) {
    const program = gl.createProgram();
    if (!program) return null;
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error(gl.getProgramInfoLog(program));
        gl.deleteProgram(program);
        return null;
    }
    return program;
}

export function getStateId(state: string) {
    switch(state) {
        case 'idle': return 0;
        case 'scanning': return 1;
        case 'executing':
        case 'processing': return 2;
        case 'self_healing': return 3;
        case 'circuit_open': return 4;
        case 'awaiting_human': return 5;
        case 'success': return 6;
        case 'failed': return 7;
        default: return 0;
    }
}

export function getBaseColor(state: string): [number, number, number] {
    switch(state) {
        case 'idle': return [0.17, 0.19, 0.23];
        case 'scanning': return [0.1, 0.5, 0.9];
        case 'executing':
        case 'processing': return [0.1, 0.8, 0.3];
        case 'self_healing': return [0.9, 0.7, 0.1];
        case 'circuit_open': return [0.7, 0.1, 0.1];
        case 'awaiting_human': return [0.5, 0.2, 0.8];
        case 'success': return [0.1, 0.9, 0.4];
        case 'failed': return [0.8, 0.1, 0.2];
        default: return [0.17, 0.19, 0.23];
    }
}

// Backward compatibility exports
export const setSujonState = setAgentState;
export const useSujonState = useAgentState;
