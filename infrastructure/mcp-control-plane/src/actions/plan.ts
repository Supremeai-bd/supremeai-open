import { ActionContext } from "../policy/risk.engine.js";

export interface ActionPlan {
  context: ActionContext;
  description: string;
  parameters: any;
  /** Function to execute the primary action. */
  executeFn: () => Promise<any>;
  /** Optional function to verify health post-execution. */
  verifyFn?: () => Promise<boolean>;
  /** Optional function to rollback if execution or verification fails. */
  rollbackFn?: () => Promise<void>;
}
