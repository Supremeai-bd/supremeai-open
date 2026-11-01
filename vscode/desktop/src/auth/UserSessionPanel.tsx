import { useEffect, useState, type FormEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';

type LoginResult = { status: string; email?: string };

const PASSKEY_ENABLED_KEY = 'supremeai.desktop.passkey_enabled.v1';
const PASSKEY_CODE_KEY = 'supremeai.desktop.passkey_pin.v1';

// User session panel: handles Supabase user auth & optional Passkey / PIN Quick-Lock.
// When Passkey / PIN protection is enabled, the workspace locks on launch or idle,
// requiring the passkey PIN to unlock while keeping the session persistent.
export default function UserSessionPanel() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [sessionEmail, setSessionEmail] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  // Passkey / Quick-Lock state
  const [passkeyEnabled, setPasskeyEnabled] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [inputPin, setInputPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [showPinSetup, setShowPinSetup] = useState(false);

  useEffect(() => {
    invoke<string | null>('user_session')
      .then((value) => setSessionEmail(value ?? null))
      .catch(() => setSessionEmail(null));

    const savedPasskey = localStorage.getItem(PASSKEY_ENABLED_KEY) === 'true';
    setPasskeyEnabled(savedPasskey);
    if (savedPasskey && localStorage.getItem(PASSKEY_CODE_KEY)) {
      setIsLocked(true);
    }
  }, []);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setNotice('');
    try {
      const result = await invoke<LoginResult>('user_login', { email, password });
      if (result.status !== 'authenticated') {
        throw new Error('The authentication service returned an invalid session.');
      }
      setSessionEmail(result.email || email);
      setExpanded(false);
    } catch (error) {
      setNotice(typeof error === 'string' ? error : error instanceof Error ? error.message : 'Sign-in failed.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      await invoke('user_logout');
    } catch {
      // Session file clearing is best-effort inside the command.
    }
    setSessionEmail(null);
    setNotice('');
    setBusy(false);
  }

  function handleUnlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const storedPin = localStorage.getItem(PASSKEY_CODE_KEY);
    if (!storedPin || inputPin === storedPin) {
      setIsLocked(false);
      setInputPin('');
      setNotice('');
    } else {
      setNotice('Incorrect PIN / Passkey.');
      setInputPin('');
    }
  }

  function togglePasskey() {
    if (passkeyEnabled) {
      localStorage.removeItem(PASSKEY_ENABLED_KEY);
      localStorage.removeItem(PASSKEY_CODE_KEY);
      setPasskeyEnabled(false);
      setShowPinSetup(false);
      setIsLocked(false);
    } else {
      setShowPinSetup(true);
    }
  }

  function saveNewPin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPin.length < 4) {
      setNotice('Passkey / PIN must be at least 4 digits.');
      return;
    }
    localStorage.setItem(PASSKEY_CODE_KEY, newPin);
    localStorage.setItem(PASSKEY_ENABLED_KEY, 'true');
    setPasskeyEnabled(true);
    setShowPinSetup(false);
    setNewPin('');
    setNotice('');
  }

  const initial = (sessionEmail || 'G').trim().charAt(0).toUpperCase();

  if (isLocked) {
    return (
      <div className="profile-row-wrap" style={{ padding: '8px 12px', background: 'rgba(15,23,42,0.85)', borderRadius: 10, border: '1px solid rgba(0,240,255,0.3)' }}>
        <form onSubmit={handleUnlock} style={{ display: 'grid', gap: '6px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 11, color: '#38bdf8' }}>
            <span>🔒</span>
            <strong>Quick-Lock Active</strong>
          </div>
          <input
            type="password"
            placeholder="Enter 4+ digit PIN"
            value={inputPin}
            onChange={(e) => setInputPin(e.target.value)}
            required
            autoFocus
            style={{ borderRadius: 6, border: '1px solid rgba(148,163,184,.3)', background: 'rgba(15,23,42,.9)', color: 'inherit', padding: '5px 8px', fontSize: 12 }}
          />
          <button type="submit" style={{ borderRadius: 6, border: 'none', background: 'linear-gradient(135deg,#00f0ff,#38bdf8)', color: '#04121c', fontWeight: 600, padding: '5px 8px', fontSize: 11, cursor: 'pointer' }}>
            Unlock
          </button>
          {notice && <small role="alert" style={{ color: '#fca5a5', fontSize: 10 }}>{notice}</small>}
        </form>
      </div>
    );
  }

  return (
    <div className="profile-row-wrap">
      <button className="profile-row" type="button" onClick={() => sessionEmail ? setExpanded(!expanded) : setExpanded(!expanded)} disabled={busy && !!sessionEmail}>
        <span className="profile-dot">{initial}</span>
        <span>
          <strong>{sessionEmail || 'Guest user'}</strong>
          <small>{sessionEmail ? `Signed in · ${passkeyEnabled ? 'Passkey Protected' : 'Session Saved'}` : 'Local chat history · tap to sign in'}</small>
        </span>
      </button>

      {expanded && !sessionEmail && (
        <form className="user-signin" onSubmit={signIn} style={{ display: 'grid', gap: '6px', padding: '10px 12px' }}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            autoComplete="username"
            onChange={(event) => setEmail(event.target.value)}
            required
            style={{ borderRadius: 8, border: '1px solid rgba(148,163,184,.25)', background: 'rgba(15,23,42,.6)', color: 'inherit', padding: '7px 10px', fontSize: 12 }}
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            style={{ borderRadius: 8, border: '1px solid rgba(148,163,184,.25)', background: 'rgba(15,23,42,.6)', color: 'inherit', padding: '7px 10px', fontSize: 12 }}
          />
          <button type="submit" disabled={busy || !email.trim() || !password} style={{ borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,#00f0ff,#38bdf8)', color: '#04121c', fontWeight: 600, padding: '7px 10px', fontSize: 12, cursor: busy ? 'wait' : 'pointer' }}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          {notice && <small role="alert" style={{ color: '#fca5a5', fontSize: 11 }}>{notice}</small>}
          <small style={{ color: 'rgba(148,163,184,.8)', fontSize: 10 }}>SupremeAI account · session stays signed in on this device</small>
        </form>
      )}

      {sessionEmail && expanded && (
        <div style={{ display: 'grid', gap: '8px', padding: '8px 12px', background: 'rgba(15,23,42,0.4)', borderRadius: 8, margin: '4px 8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11 }}>
            <span>Passkey / PIN Lock:</span>
            <button
              type="button"
              onClick={togglePasskey}
              style={{
                borderRadius: 6,
                border: '1px solid rgba(148,163,184,.3)',
                background: passkeyEnabled ? 'rgba(0,240,255,0.15)' : 'transparent',
                color: passkeyEnabled ? '#38bdf8' : 'inherit',
                padding: '3px 8px',
                fontSize: 10,
                cursor: 'pointer'
              }}
            >
              {passkeyEnabled ? 'Enabled (ON)' : 'Disabled (OFF)'}
            </button>
          </div>

          {showPinSetup && (
            <form onSubmit={saveNewPin} style={{ display: 'grid', gap: '4px' }}>
              <input
                type="password"
                placeholder="Set 4+ digit PIN"
                value={newPin}
                onChange={(e) => setNewPin(e.target.value)}
                required
                style={{ borderRadius: 6, border: '1px solid rgba(148,163,184,.3)', background: 'rgba(15,23,42,.8)', color: 'inherit', padding: '4px 6px', fontSize: 11 }}
              />
              <button type="submit" style={{ borderRadius: 6, border: 'none', background: '#38bdf8', color: '#04121c', fontWeight: 600, padding: '4px', fontSize: 11, cursor: 'pointer' }}>
                Save Passkey PIN
              </button>
            </form>
          )}

          {passkeyEnabled && (
            <button
              type="button"
              onClick={() => setIsLocked(true)}
              style={{ borderRadius: 6, border: '1px solid rgba(0,240,255,0.3)', background: 'transparent', color: '#38bdf8', padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}
            >
              Lock Workspace Now
            </button>
          )}

          <button
            className="user-signout"
            type="button"
            onClick={() => void signOut()}
            disabled={busy}
            style={{ borderRadius: 6, border: '1px solid rgba(239,68,68,.3)', background: 'transparent', color: '#fca5a5', padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}
          >
            Sign out
          </button>
          {notice && <small role="alert" style={{ color: '#fca5a5', fontSize: 10 }}>{notice}</small>}
        </div>
      )}
    </div>
  );
}
