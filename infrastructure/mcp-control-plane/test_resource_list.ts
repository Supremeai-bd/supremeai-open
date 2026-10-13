/**
 * INTEGRATION test — requires a LIVE tower on http://localhost:3771 (#123).
 *
 * This used to run inside `test:unit`; its ECONNREFUSED exit-1 broke the whole
 * `&&` chain in every server-less environment (local dev, CI without a tower).
 * It now ships as `npm run test:integration` and is intentionally NOT part of
 * the unit chain.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
// বাংলা: সার্ভারের /mcp এন্ডপয়েন্ট StreamableHTTPServerTransport ব্যবহার করে
// (src/index.ts — "SupremeAI Control Tower → http://localhost:3771/mcp")।
// SSE legacy ক্লায়েন্টদের জন্য আলাদা /sse রুট আছে। এই টেস্ট আগে
// SSEClientTransport দিয়ে /mcp-তে যাচ্ছিল — প্রোটোকল মিসম্যাচে SSE handshake
// HTTP 400 পেত; এখন সার্ভারের প্রাইমারি ট্রান্সপোর্টের সাথে সঠিকভাবে যুক্ত হয়।
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

async function main() {
  const transport = new StreamableHTTPClientTransport(new URL("http://localhost:3771/mcp"));
  const client = new Client({ name: "test-client", version: "1.0.0" });
  await client.connect(transport);

  console.log("Connected to MCP server");

  const result = await client.callTool({
    name: "resource.list",
    arguments: {}
  });

  console.log(JSON.stringify(result, null, 2));

  await client.close();
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
