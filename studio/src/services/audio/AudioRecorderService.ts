export class AudioRecorderService {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private websocket: WebSocket | null = null;
  private isRecording: boolean = false;
  private onTranscriptCallback: ((text: string) => void) | null = null;

  private wsUrl: string;

  constructor(wsUrl: string) {
    this.wsUrl = wsUrl;
  }

  public onTranscript(callback: (text: string) => void) {
    this.onTranscriptCallback = callback;
  }

  public async startRecording() {
    if (this.isRecording) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      this.audioChunks = [];

      this.connectWebSocket();

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
          // Send chunk directly via WebSocket for real-time streaming
          if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(event.data);
          }
        }
      };

      // Chunk every 500ms
      this.mediaRecorder.start(500);
      this.isRecording = true;
      console.warn('🎙️ [AudioRecorderService] Started recording...');
    } catch (error) {
      console.error('❌ [AudioRecorderService] Microphone access denied:', error);
      throw error;
    }
  }

  public stopRecording() {
    if (!this.isRecording || !this.mediaRecorder) return;

    this.mediaRecorder.stop();
    this.mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    this.isRecording = false;
    console.warn('🛑 [AudioRecorderService] Stopped recording.');

    // Signal backend to process the buffer
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify({ action: 'process' }));
    }
  }

  public sendText(text: string) {
    this.connectWebSocket();
    const payload = JSON.stringify({ action: 'text_chat', text });

    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(payload);
    } else if (this.websocket) {
      // If it's still connecting, wait for open
      this.websocket.addEventListener('open', () => {
        this.websocket?.send(payload);
      }, { once: true });
    }
  }

  public isConnected(): boolean {
    return this.websocket !== null && this.websocket.readyState === WebSocket.OPEN;
  }

  private connectWebSocket() {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) return;

    this.websocket = new WebSocket(this.wsUrl);

    this.websocket.onopen = () => {
      console.warn('🟢 [AudioRecorderService] WebSocket connected.');
    };

    this.websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'transcript' && this.onTranscriptCallback) {
          this.onTranscriptCallback(data.text);
        } else if (data.type === 'response_chunk') {
          // This goes to the playback service via global event or store,
          // but for simplicity, we dispatch a custom event
          window.dispatchEvent(new CustomEvent('supremeai_speak', { detail: data.text }));
        }
      } catch (e) {
        console.warn('⚠️ [AudioRecorderService] Received non-JSON message or error parsing.', e);
      }
    };

    this.websocket.onerror = (error) => {
      console.error('❌ [AudioRecorderService] WebSocket Error:', error);
    };

    this.websocket.onclose = () => {
      console.warn('🔴 [AudioRecorderService] WebSocket closed.');
      this.websocket = null;
    };
  }
}
