/**
 * JIT OTP Dialog Utility for SupremeAI VS Code Extension.
 *
 * Prompts user for Just-In-Time OTP code and reason before executing destructive actions.
 */

import * as vscode from 'vscode';

export interface JitOtpResult {
  otpCode: string;
  reason: string;
  cancelled: boolean;
}

export class JitOtpDialog {
  /**
   * Shows a VS Code input dialog asking for JIT OTP and reason.
   */
  public static async promptForOtp(actionName: string): Promise<JitOtpResult> {
    const reason = await vscode.window.showInputBox({
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

    const otpCode = await vscode.window.showInputBox({
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
}
