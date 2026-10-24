import * as vscode from 'vscode';
import { AuthService } from '../services/AuthService';

export class AuthHandler {
  public static registerAuthCallback(context: vscode.ExtensionContext): void {
    const authSuccessDisposable = vscode.window.registerUriHandler({
      handleUri: async (uri: vscode.Uri) => {
        console.log('[SupremeAI] URI callback received:', uri.toString());

        if (uri.query.includes('action=login') || uri.path.includes('callback')) {
          const params = new URLSearchParams(uri.query);
          const token = params.get('token');
          const userParam = params.get('user');
          const stateParam = params.get('state');

          if (token) {
            const auth = AuthService.getInstance();
            if (auth) {
              // Verify CSRF state
              const savedState = auth.getAuthState();
              if (savedState && stateParam !== savedState) {
                vscode.window.showErrorMessage('Login failed: Invalid state parameter (CSRF protection).');
                return;
              }
              auth.clearAuthState();

              vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Verifying authentication...',
                cancellable: false
              }, async () => {
                const isValid = await auth.verifyToken(token);
                if (!isValid) {
                  vscode.window.showErrorMessage('Login failed: Invalid or expired token.');
                  return;
                }

                auth.setToken(token);
                if (userParam) {
                  try {
                    const user = JSON.parse(decodeURIComponent(userParam));
                    auth.setUser(user);
                  } catch (e) {
                    console.error('[SupremeAI] Failed to parse user data from URI:', e);
                    const profile = await auth.fetchUserProfile(token);
                    auth.setUser(profile || { username: 'User' });
                  }
                } else {
                  const profile = await auth.fetchUserProfile(token);
                  auth.setUser(profile || { username: 'User' });
                }
                vscode.window.showInformationMessage('Login successful! Welcome to SupremeAI.');
              });
            }
          }
        }
      }
    });
    context.subscriptions.push(authSuccessDisposable);
  }
}
