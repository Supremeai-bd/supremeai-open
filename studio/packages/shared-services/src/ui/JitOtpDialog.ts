/**
 * JIT OTP Dialog — Platform-Agnostic Just-In-Time OTP prompting utility.
 *
 * VS Code-এ native showInputBox ব্যবহার হয়; desktop এ React-based dialog ব্যবহার হয়।
 * এই abstract version থেকে একটা helper ফাংশন দেওয়া হয়, যা কাজের আগে
 * নিরাপদভাবে OTP + reason যাচাই করে।
 */

import type { PlatformPrompt } from '../platform';

export interface JitOtpResult {
  otpCode: string;
  reason: string;
  cancelled: boolean;
}

/**
 * অ্যাকশনের আগে JIT OTP + reason নিতে প্ল্যাটফর্ম প্রম্পট ব্যবহার করে।
 * validateInput সহ showInputBox টা platform adapter-এ থাকবে।
 */
export async function promptForOtp(
  prompt: PlatformPrompt,
  actionName: string
): Promise<JitOtpResult> {
  // Reason ইনপুট
  const reason = await prompt.showInputBox({
    title: `🔐 JIT OTP Required for '${actionName}'`,
    prompt: 'Enter reason for executing this sensitive action (min 5 chars):',
    placeHolder: 'e.g. Approved emergency deployment to target workspace',
    validateInput: (value) => {
      if (!value || value.trim().length < 5) {
        return 'Reason must be at least 5 characters long';
      }
      return null;
    },
  });

  if (!reason) {
    return { otpCode: '', reason: '', cancelled: true };
  }

  // OTP ইনপুট
  const otpCode = await prompt.showInputBox({
    title: `🔐 JIT OTP Code for '${actionName}'`,
    prompt: 'Enter 6-digit Authenticator OTP code:',
    placeHolder: '123456',
    password: true,
    validateInput: (value) => {
      if (!value || !/^\d{6}$/.test(value.trim())) {
        return 'OTP code must be 6 digits';
      }
      return null;
    },
  });

  if (!otpCode) {
    return { otpCode: '', reason: '', cancelled: true };
  }

  return {
    otpCode: otpCode.trim(),
    reason: reason.trim(),
    cancelled: false,
  };
}

/**
 * একটি দ্রুত OTP-validate check — OTP 6-digit নাকি না।
 */
export function isValidOtp(value: string): boolean {
  return /^\d{6}$/.test(value.trim());
}