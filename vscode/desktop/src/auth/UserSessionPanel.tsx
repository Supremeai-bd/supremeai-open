import { useEffect, useState, type FormEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';

type LoginResult = { status: string; email?: string };

// User session panel (2026-11-01): replaces the hardcoded "Guest user" row.
// Sign-in is backed by the Rust user_login/user_logout/user_session commands
// (Supabase auth, session persisted in the OS app-config dir). Chat history
// stays local as before; sign-in only changes the workspace identity.
export default function UserSessionPanel() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [sessionEmail, setSessionEmail] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    invoke<string | null>('user_session')
      .then((value) => setSessionEmail(value ?? null))
      .catch(() => setSessionEmail(null));
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

  const initial = (sessionEmail || 'G').trim().charAt(0).toUpperCase();

  return (
    <div className="profile-row-wrap">
      <button className="profile-row" type="button" onClick={() => sessionEmail ? void signOut() : setExpanded(!expanded)} disabled={busy && !!sessionEmail}>
        <span className="profile-dot">{initial}</span>
        <span>
          <strong>{sessionEmail || 'Guest user'}</strong>
          <small>{sessionEmail ? 'Signed in · history stays on this device' : 'Local chat history · tap to sign in'}</small>
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
        <button className="user-signout" type="button" onClick={() => void signOut()} disabled={busy} style={{ margin: '6px 12px', borderRadius: 8, border: '1px solid rgba(148,163,184,.25)', background: 'transparent', color: 'inherit', padding: '6px 10px', fontSize: 11, cursor: 'pointer' }}>
          Sign out
        </button>
      )}
    </div>
  );
}
