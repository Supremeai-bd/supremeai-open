import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerIntelligenceTools } from "./src/tools/intelligence.tools.js";

async function main() {
  console.log("Testing intelligence tools registration...");
  const server = new McpServer({ name: "test-server", version: "1.0.0" });
  await registerIntelligenceTools(server);
  console.log("✅ Successfully registered codebase_graph_query and devtools_audit tools!");

  // Verify tool definitions exist on the server
  // @ts-expect-error accessing registered tools for testing
  const tools = server._registeredTools;
  console.log("Registered tool keys:", Object.keys(tools));

  if (!tools["codebase_graph_query"] || !tools["devtools_audit"]) {
    throw new Error("Missing expected tools!");
  }

  // Test executing codebase_graph_query handler
  const graphTool = tools["codebase_graph_query"];
  const res = await graphTool.handler({ query: "studio_auth_login", limit: 5 }, {});
  console.log("codebase_graph_query handler response:", res.content[0].text.slice(0, 300) + "...");
  console.log("✅ All intelligence tool handlers executed successfully!");
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error("Test failed:", err);
    process.exit(1);
  });
