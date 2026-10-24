/**
 * ScopeGuardService — Dynamic permission scope for target repositories
 * Protected main repos default to READ_ONLY; explicit JIT OTP binding enables write.
 *
 * Platform-Agnostic: VS Code extension ও Electron desktop app দুটোই ব্যবহার করতে পারবে।
 */

export const PermissionScope = {
  READ_ONLY: 'READ_ONLY',
  READ_WRITE: 'READ_WRITE',
  ADMIN: 'ADMIN',
} as const;

export type PermissionScope = typeof PermissionScope[keyof typeof PermissionScope];

export class ScopeGuardService {
  private static instance: ScopeGuardService | null = null;
  private currentScope: PermissionScope = PermissionScope.READ_ONLY;

  private constructor() {
    /* singleton */
  }

  public static getInstance(): ScopeGuardService {
    if (!ScopeGuardService.instance) {
      ScopeGuardService.instance = new ScopeGuardService();
    }
    return ScopeGuardService.instance;
  }

  public static resetInstance(): void {
    ScopeGuardService.instance = null;
  }

  public async detectCurrentScope(): Promise<PermissionScope> {
    // Protected main repos default to READ_ONLY
    // In future: check against backend admin-api for JIT OTP status
    return this.currentScope;
  }

  public isReadOnly(): boolean {
    return this.currentScope === PermissionScope.READ_ONLY;
  }

  public canWrite(): boolean {
    return this.currentScope === PermissionScope.READ_WRITE;
  }

  public isAdmin(): boolean {
    return this.currentScope === PermissionScope.ADMIN;
  }

  public async elevateScope(newScope: PermissionScope): Promise<boolean> {
    // Future: verify JIT OTP before elevating scope
    this.currentScope = newScope;
    return true;
  }
}