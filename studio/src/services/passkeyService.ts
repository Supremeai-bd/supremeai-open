/**
 * studio/src/services/passkeyService.ts
 * Browser-native WebAuthn client helper for Passkey / Fingerprint authentication.
 * Uses native navigator.credentials with zero external npm dependencies.
 */

// Helper to convert base64url string to Uint8Array
export function bufferFromBase64Url(base64Url: string): Uint8Array {
  const padding = '='.repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Helper to convert ArrayBuffer to base64url string
export function bufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function isPasskeySupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.PublicKeyCredential !== undefined &&
    typeof window.PublicKeyCredential === 'function'
  );
}

export async function isPlatformBiometricAvailable(): Promise<boolean> {
  if (!isPasskeySupported()) return false;
  try {
    return await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

export interface RegisterPasskeyParams {
  userId?: string;
  email?: string;
  role?: 'user' | 'admin';
  displayName?: string;
  deviceName?: string;
}

export async function registerPasskey(params: RegisterPasskeyParams): Promise<{ status: string; message: string; passkey?: any }> {
  if (!isPasskeySupported()) {
    throw new Error('WebAuthn / Passkeys are not supported on this browser or platform.');
  }

  // 1. Fetch registration options from server
  const optRes = await fetch('/api/auth/passkey/register/options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: params.userId,
      email: params.email,
      role: params.role || 'user',
      display_name: params.displayName,
    }),
  });

  if (!optRes.ok) {
    const errData = await optRes.json().catch(() => ({}));
    throw new Error(errData.detail || 'Failed to fetch passkey registration options');
  }

  const options = await optRes.json();

  // 2. Prepare credential creation options (buffers)
  const publicKeyCreationOptions: CredentialCreationOptions = {
    publicKey: {
      ...options,
      challenge: bufferFromBase64Url(options.challenge).buffer as ArrayBuffer,
      user: {
        ...options.user,
        id: bufferFromBase64Url(options.user.id),
      },
      pubKeyCredParams: options.pubKeyCredParams,
    },
  };

  // 3. Prompt user for Biometric / Touch ID / Fingerprint
  const credential = (await navigator.credentials.create(publicKeyCreationOptions)) as PublicKeyCredential | null;
  if (!credential) {
    throw new Error('Passkey creation cancelled or rejected');
  }

  const rawResponse = credential.response as AuthenticatorAttestationResponse;

  // 4. Send attestation to server for cryptographic verification
  const verifyRes = await fetch('/api/auth/passkey/register/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      clientDataJSON: bufferToBase64Url(rawResponse.clientDataJSON),
      attestationObject: bufferToBase64Url(rawResponse.attestationObject),
      device_name: params.deviceName || 'Personal Biometric Device',
    }),
  });

  if (!verifyRes.ok) {
    const errData = await verifyRes.json().catch(() => ({}));
    throw new Error(errData.detail || 'Passkey verification failed');
  }

  return await verifyRes.json();
}

export async function loginWithPasskey(role: 'user' | 'admin' = 'user'): Promise<{ status: string; access_token: string; role: string; user_id: string; device_name?: string }> {
  if (!isPasskeySupported()) {
    throw new Error('WebAuthn / Passkeys are not supported on this browser or platform.');
  }

  // 1. Fetch authentication options
  const optRes = await fetch('/api/auth/passkey/login/options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });

  if (!optRes.ok) {
    const errData = await optRes.json().catch(() => ({}));
    throw new Error(errData.detail || 'Failed to initialize biometric login');
  }

  const options = await optRes.json();

  // 2. Prepare credential request options
  const publicKeyRequestOptions: CredentialRequestOptions = {
    publicKey: {
      challenge: bufferFromBase64Url(options.challenge).buffer as ArrayBuffer,
      timeout: options.timeout,
      rpId: options.rpId,
      userVerification: options.userVerification || 'required',
    },
  };

  // 3. Prompt user for Fingerprint
  const assertion = (await navigator.credentials.get(publicKeyRequestOptions)) as PublicKeyCredential | null;
  if (!assertion) {
    throw new Error('Passkey login cancelled or failed');
  }

  const rawResponse = assertion.response as AuthenticatorAssertionResponse;

  // 4. Verify assertion signature on server
  const verifyRes = await fetch('/api/auth/passkey/login/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: assertion.id,
      rawId: bufferToBase64Url(assertion.rawId),
      response: {
        clientDataJSON: bufferToBase64Url(rawResponse.clientDataJSON),
        authenticatorData: bufferToBase64Url(rawResponse.authenticatorData),
        signature: bufferToBase64Url(rawResponse.signature),
        userHandle: rawResponse.userHandle ? bufferToBase64Url(rawResponse.userHandle) : null,
      },
    }),
  });

  if (!verifyRes.ok) {
    const errData = await verifyRes.json().catch(() => ({}));
    throw new Error(errData.detail || 'Biometric authentication rejected');
  }

  return await verifyRes.json();
}

export async function listUserPasskeys(userId: string) {
  const res = await fetch(`/api/auth/passkey/devices?user_id=${encodeURIComponent(userId)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.devices || [];
}

export async function revokePasskey(credentialId: string, userId: string) {
  const res = await fetch(`/api/auth/passkey/devices/${encodeURIComponent(credentialId)}?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  });
  return res.ok;
}
