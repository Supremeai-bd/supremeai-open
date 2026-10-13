import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";
config({ path: path.resolve(process.cwd(), "../../.env") });
import { getWorkflowRuns, listSecrets } from "./src/adapters/github/index.js";

async function main() {
  const githubId = "github-primary";
  try {
    const runs = await getWorkflowRuns(githubId, 1);
    console.log("Runs:", JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error("Error runs:", e);
  }
  
  try {
    const secrets = await listSecrets(githubId);
    console.log("Secrets:", JSON.stringify(secrets, null, 2));
  } catch (e) {
    console.error("Error secrets:", e);
  }
}
main();
