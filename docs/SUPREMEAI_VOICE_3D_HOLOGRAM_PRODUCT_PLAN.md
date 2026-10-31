# SupremeAI Voice + 3D Hologram Product Plan

## Vision

SupremeAI Desktop can evolve from a chat window into an ambient intelligence workspace: the user speaks naturally, the assistant listens and responds with voice, while a responsive 3D hologram-style character communicates state, attention, confidence, and progress.

The first version should focus on a polished **hologram-style desktop interface**, not claim to be a physical volumetric hologram. It can use WebGL/WebGPU, translucent layers, particles, lighting, and audio-reactive motion to create a convincing futuristic presence on a normal monitor. Support for Looking Glass, AR glasses, or physical holographic displays can be added later through an adapter layer.

## Product experience

### Core interaction loop

1. The user presses a push-to-talk shortcut or clicks the hologram microphone.
2. The hologram shifts into a listening state with a soft blue/acid-green pulse.
3. Speech is transcribed locally or through an approved speech service.
4. The assistant shows a short intent preview before taking an external action.
5. The model streams a response in text and voice at the same time.
6. The hologram animates according to the response state: thinking, speaking, warning, success, or waiting.
7. The user can interrupt the assistant at any time with voice or a stop button.

### Interaction modes

- **Push-to-talk:** safest default; microphone is active only while held.
- **Click-to-talk:** useful for desktop accessibility.
- **Hands-free session:** optional, explicit opt-in mode with a visible microphone indicator.
- **Wake phrase:** optional future feature; must have an obvious on/off state.
- **Silent mode:** text-only responses while keeping the 3D assistant state active.

## Hologram state system

The 3D layer should be state-driven rather than decorative. Every state should communicate useful information without requiring the user to read text.

| State | Visual behavior | Voice behavior |
|---|---|---|
| Idle | Slow breathing glow, low particle movement | No microphone access |
| Listening | Ring expands with input volume, waveform appears | Records speech |
| Transcribing | Thin scanning line, subtle orbit rotation | Optional short sound cue |
| Thinking | Core rotates slowly, particles converge | No speech or a brief acknowledgement |
| Speaking | Mouth/face motion or waveform sync, brighter aura | Streams TTS audio |
| Tool execution | Orbit changes color, progress nodes appear | Announces important actions only |
| Needs approval | Amber pulse, shield icon | Asks for confirmation |
| Success | Green pulse and particles disperse | Short completion tone |
| Error/offline | Warm red/amber pulse, reduced motion | Explains recovery action |

## Recommended technical architecture

```text
React/Tauri Desktop
├── Voice Controller
│   ├── microphone permission state
│   ├── push-to-talk / hands-free controls
│   ├── audio level meter
│   └── interruption handling
│
├── Speech Layer
│   ├── Speech-to-text adapter
│   ├── text-to-speech adapter
│   ├── voice activity detection
│   └── local/cloud provider policy
│
├── Conversation Runtime
│   ├── streaming Gateway request
│   ├── skill/plugin routing
│   ├── tool approval gates
│   └── session state
│
├── Hologram Renderer
│   ├── WebGL/WebGPU scene
│   ├── state machine
│   ├── audio-reactive animation
│   └── accessibility fallback
│
└── SupremeAI MCP Tower
    ├── governed tool execution
    ├── permissions
    ├── vault references
    ├── audit logs
    └── plugin/skill registry
```

## Voice layer design

### Speech-to-text

Use an adapter interface so the app is not locked to one provider:

```ts
export interface SpeechToTextProvider {
  start(options: { language: string; interimResults: boolean }): Promise<void>;
  stop(): Promise<{ text: string; confidence?: number }>;
  cancel(): Promise<void>;
}
```

The provider can be local or remote. The UI should always show whether audio is processed locally or sent to a cloud service.

### Text-to-speech

Use streaming speech where possible. The assistant should begin speaking after a complete sentence or short phrase rather than waiting for the entire response.

```ts
export interface TextToSpeechProvider {
  speak(text: string, options: { voice: string; speed: number }): Promise<void>;
  stop(): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
}
```

Important controls:

- voice selection
- speaking speed
- pronunciation rules
- language and accent
- interrupt/cancel
- text-only fallback
- mute shortcut

### Interruption model

Interruption is essential for a natural assistant. When the user speaks while the assistant is speaking:

1. Stop TTS immediately.
2. Cancel or ignore the current audio segment.
3. Preserve the partial assistant text.
4. Start a new input capture.
5. Mark the interrupted response as resumable.

The first implementation can stop TTS and ignore late audio. A later native implementation can cancel the Gateway request with a request ID.

## Hologram implementation options

### Option A: Lightweight 2.5D hologram

Best for the first release.

- SVG rings
- CSS particles
- Canvas waveform
- layered gradients
- scanlines and glow
- audio-reactive scale

Advantages:

- low startup cost
- small bundle
- works on low-end hardware
- easy to theme
- no 3D model pipeline required

### Option B: WebGL avatar

Best for the second phase.

- Three.js or Babylon.js
- GLB avatar model
- skeletal animation
- facial blendshapes
- emissive materials
- post-processing glow

Recommended scene structure:

```text
HologramScene
├── AmbientParticles
├── OrbitRings
├── AvatarModel
├── AudioWaveform
├── StateEffects
└── InteractionTarget
```

### Option C: External holographic display adapter

For future hardware integrations:

```ts
interface HologramOutputAdapter {
  connect(): Promise<void>;
  setScene(scene: HologramSceneState): Promise<void>;
  disconnect(): Promise<void>;
}
```

The desktop application should not depend on a specific display vendor. The same state model can drive a monitor, AR glasses, or a physical display.

## Skills and plugins with voice

Every skill/plugin should declare whether it supports voice:

```json
{
  "voice": {
    "enabled": true,
    "inputModes": ["push_to_talk", "click_to_talk"],
    "outputModes": ["speech", "text"],
    "requiresConfirmationBeforeTools": true
  }
}
```

Examples:

- “Research this topic” starts a research skill.
- “Summarize this document” opens the file picker or uses the active document.
- “Create a task for tomorrow” requires confirmation before writing to a task service.
- “Send this email” always requires a final confirmation.
- “Open my GitHub issues” can use a read-only plugin permission.

Voice commands should map to the same structured skill inputs used by chat and the Marketplace. This keeps skills reusable across desktop, web, and automation workflows.

## Safety and privacy

Voice features need stronger privacy controls than normal chat.

### User-visible controls

- microphone status always visible
- one-click mute
- clear recording indicator
- local/cloud processing label
- session recording disabled by default
- transcript retention setting
- delete voice history option
- per-plugin microphone permission
- per-action confirmation for external side effects

### Permission categories

```text
microphone.listen
voice.transcribe
voice.synthesize
read_active_window
read_local_files
network.access
external_account.access
execute_tool
write_external_data
```

Sensitive actions should never be triggered solely by an ambiguous voice command. The assistant should display a confirmation card for payments, messages, account changes, file deletion, or public posting.

## Performance strategy

The 3D and voice layer must not make the chat app feel heavy.

### Rendering

- use a low-cost 2.5D mode by default
- pause particles when the window is hidden
- reduce effects on battery power
- honor `prefers-reduced-motion`
- use a low-detail avatar on integrated graphics
- render the hologram at a lower internal resolution
- avoid continuous heavy post-processing

### Streaming

- batch incoming tokens every 30–60 ms
- render plain text while a response is streaming
- enable Markdown rendering after completion or on a debounce
- debounce local history persistence
- only auto-scroll when the user is near the bottom
- reuse one native HTTP client

### Voice

- use voice activity detection to avoid sending silence
- stream TTS by sentence
- stop audio immediately on interruption
- cache short system sounds
- avoid repeated permission checks during a session

## Standout features that would make the product memorable

### 1. Spatial memory map

The hologram can show a small constellation of active projects, conversations, and skills. Selecting a node opens the relevant chat or workspace.

### 2. Focus mode

The hologram becomes a quiet ambient companion while the user works. It only speaks for urgent events or when called.

### 3. Live task runway

When the assistant is executing multiple tool steps, show a visible path:

```text
Understand → Search → Compare → Draft → Review
```

Each step can expand to show the tool and permission used.

### 4. Explainability pulse

Instead of exposing hidden chain-of-thought, show a safe high-level activity summary:

- interpreting request
- checking available tools
- gathering information
- drafting response
- verifying format

### 5. Voice personas without locking the system

Allow voice styles such as Calm, Direct, Warm, and Technical, but keep the underlying model and skill separate from the voice persona.

### 6. Hologram focus companion

The assistant can react to the selected application or active project without recording the screen by default. It can show reminders, timers, and progress while keeping the main conversation available.

### 7. Multi-agent stage

Show multiple small holographic nodes for specialist skills, such as Researcher, Writer, Coder, and Reviewer. This should represent tool roles, not expose private reasoning.

## Phased implementation plan

### Phase 1: Voice-ready foundation

- Add microphone permission state
- Add push-to-talk button and shortcut
- Add speech provider interfaces
- Add text-to-speech provider interface
- Add mute and stop controls
- Add voice settings model
- Add audio level indicator
- Add voice privacy disclosure

### Phase 2: 2.5D hologram

- Build a state-driven hologram component
- Add idle/listening/thinking/speaking/error states
- Add audio-reactive waveform
- Add reduced-motion and low-power modes
- Add theme-aware colors
- Keep the component independent of the chat runtime

### Phase 3: Streaming voice

- Stream Gateway text
- split response into sentence-sized TTS chunks
- synchronize text and voice state
- implement interruption
- add voice output settings

### Phase 4: Marketplace and skills

- Add voice capability to plugin manifests
- connect voice commands to structured skill inputs
- show permission cards before tool execution
- add plugin-specific voice settings
- reuse the same skill runtime in chat and voice modes

### Phase 5: WebGL avatar and hardware adapters

- add optional GLB avatar
- implement animation state machine
- add GPU capability detection
- add external hologram output adapter
- add performance diagnostics

## Recommended first milestone

The most valuable first milestone is not a full 3D avatar. It is:

1. Push-to-talk voice input.
2. Streaming TTS output with interruption.
3. A lightweight 2.5D hologram state component.
4. A clear microphone/privacy indicator.
5. One reusable voice-enabled skill, such as Web Researcher.
6. A visible approval card before external tool actions.

This creates a convincing product experience quickly, keeps the architecture reusable, and avoids committing early to expensive 3D assets or a single voice provider.

## Success metrics

Track measurable outcomes:

- time from microphone press to transcript
- time to first spoken response
- interruption response time
- speech recognition accuracy
- task completion rate by voice
- percentage of users who enable hands-free mode
- CPU/GPU usage while hologram is idle
- battery impact on laptops
- tool approval completion rate
- voice feature retention after one week

## Final recommendation

Build SupremeAI as a **voice-first, skill-driven intelligence workspace** with a lightweight hologram layer. Keep the assistant's capabilities separate from its visual form, voice, model, and tool providers.

The reusable foundation should be:

```text
Skill manifest
+ Voice adapter
+ Tool permissions
+ Conversation runtime
+ Hologram state machine
+ MCP Tower governance
```

That structure allows the same skill to work through text, voice, desktop, web, automation, and future holographic hardware without rewriting the core capability each time.
