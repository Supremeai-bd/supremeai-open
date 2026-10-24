import { useEffect, useRef, useState } from 'react';
import { useSessionCockpitStore, type SujonState } from '../store/sessionCockpitStore';
// বাংলা মন্তব্য: utility functions একে অপর ফাইল থেকে ইম্পোর্ট করা হয়েছে, যাতে react-refresh সতর্কতা দূর হয়
import {
  vertexShaderSource,
  fragmentShaderSource,
  createShader,
  createProgram,
  getBaseColor,
  getStateId,
} from './sujon-utils';

// বাংলা মন্তব্য: Re-export for DashboardShell
export type { SujonState };

export function AgentStateShaderBackground({ state: forcedState }: { state?: SujonState }) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [eventState, setEventState] = useState<SujonState>('idle');
    const sessionState = useSessionCockpitStore((state) => state.agentState);
    const sessionId = useSessionCockpitStore((state) => state.sessionId);

    // If we are in a session, prefer session state over ambient event state
    const effectiveState = forcedState ?? (sessionId ? sessionState : eventState);

    const animationRef = useRef<number>(0);
    const glRef = useRef<WebGL2RenderingContext | null>(null);
    const programRef = useRef<WebGLProgram | null>(null);
    const bufferRef = useRef<WebGLBuffer | null>(null);
    const texCoordBufferRef = useRef<WebGLBuffer | null>(null);
    const vaoRef = useRef<WebGLVertexArrayObject | null>(null);

    // Listen for Sujon state changes
    useEffect(() => {
      const onState = (e: Event) => setEventState((e as CustomEvent<SujonState>).detail);
      window.addEventListener('supremeai:sujon-state', onState);
      return () => window.removeEventListener('supremeai:sujon-state', onState);
    }, []);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const gl = canvas.getContext('webgl2', { antialias: false, alpha: true, depth: false });
        if (!gl) {
            console.error('WebGL2 not supported');
            return;
        }
        glRef.current = gl;

        const vShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
        const fShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);
        if (!vShader || !fShader) return;

        const program = createProgram(gl, vShader, fShader);
        if (!program) return;
        programRef.current = program;

        gl.deleteShader(vShader);
        gl.deleteShader(fShader);

        const positionAttributeLocation = gl.getAttribLocation(program, 'a_position');
        const texCoordAttributeLocation = gl.getAttribLocation(program, 'a_texCoord');

        const positionBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
        const positions = new Float32Array([
            -1, -1,
             1, -1,
            -1,  1,
            -1,  1,
             1, -1,
             1,  1,
        ]);
        gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
        bufferRef.current = positionBuffer;

        const vao = gl.createVertexArray();
        gl.bindVertexArray(vao);
        vaoRef.current = vao;

        gl.enableVertexAttribArray(positionAttributeLocation);
        gl.vertexAttribPointer(positionAttributeLocation, 2, gl.FLOAT, false, 0, 0);

        const texCoordBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
            0, 0,
            1, 0,
            0, 1,
            0, 1,
            1, 0,
            1, 1,
        ]), gl.STATIC_DRAW);
        texCoordBufferRef.current = texCoordBuffer;

        gl.enableVertexAttribArray(texCoordAttributeLocation);
        gl.vertexAttribPointer(texCoordAttributeLocation, 2, gl.FLOAT, false, 0, 0);

        const timeLocation = gl.getUniformLocation(program, 'u_time');
        const resolutionLocation = gl.getUniformLocation(program, 'u_resolution');

        let startTime = performance.now();
        let isVisible = document.visibilityState === 'visible';

        const handleVisibilityChange = () => {
            isVisible = document.visibilityState === 'visible';
            if (isVisible) {
                startTime = performance.now() - (animationRef.current || 0) * 1000;
                render(performance.now());
            }
        };
        document.addEventListener('visibilitychange', handleVisibilityChange);

        const resizeCanvas = () => {
            if (!canvas) return;
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            gl.viewport(0, 0, gl.canvas.width, gl.canvas.height);
        };
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();


        const render = (now: number) => {
            if (!isVisible || !glRef.current) return;

            const time = (now - startTime) * 0.001;

            gl.useProgram(program);
            gl.bindVertexArray(vao);

            gl.uniform1f(timeLocation, time);
            gl.uniform2f(resolutionLocation, gl.canvas.width, gl.canvas.height);

            // Note: In React, accessing effectiveState directly in this closure might hold stale value unless we ref it.
            // But since this effect re-runs on nothing (dependencies array []), we need to use a ref to get latest state,
            // OR include effectiveState in dependencies. But rebuilding WebGL context on state change is bad.
            // Instead, we will use a ref for the effectiveState. Let's fix that.

            gl.clearColor(0, 0, 0, 0);
            gl.clear(gl.COLOR_BUFFER_BIT);
            gl.drawArrays(gl.TRIANGLES, 0, 6);

            animationRef.current = requestAnimationFrame(render);
        };

        animationRef.current = requestAnimationFrame(render);

        return () => {
            document.removeEventListener('visibilitychange', handleVisibilityChange);
            window.removeEventListener('resize', resizeCanvas);
            if (animationRef.current) cancelAnimationFrame(animationRef.current);
            if (glRef.current) {
                const glCtx = glRef.current;
                if (programRef.current) glCtx.deleteProgram(programRef.current);
                if (bufferRef.current) glCtx.deleteBuffer(bufferRef.current);
                if (texCoordBufferRef.current) glCtx.deleteBuffer(texCoordBufferRef.current);
                if (vaoRef.current) glCtx.deleteVertexArray(vaoRef.current);
                const ext = glCtx.getExtension('WEBGL_lose_context');
                if (ext) ext.loseContext();
            }
        };
    }, []); // Run once to initialize context

    // Update uniforms when state changes
    useEffect(() => {
        if (!glRef.current || !programRef.current) return;
        const gl = glRef.current;
        gl.useProgram(programRef.current);
        const colorLocation = gl.getUniformLocation(programRef.current, 'u_baseColor');
        const intensityLocation = gl.getUniformLocation(programRef.current, 'u_intensity');
        const stateIdLocation = gl.getUniformLocation(programRef.current, 'u_stateId');

        const color = getBaseColor(effectiveState);
        gl.uniform3f(colorLocation, color[0], color[1], color[2]);
        gl.uniform1f(intensityLocation, 1.0);
        gl.uniform1i(stateIdLocation, getStateId(effectiveState));
    }, [effectiveState]);

    return (
        <canvas
            ref={canvasRef}
            className="fixed inset-0 z-[-1] pointer-events-none w-full h-full opacity-60 transition-opacity duration-1000"
            style={{ contain: 'strict' }}
        />
    );
}
