import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";
config({ path: path.resolve(process.cwd(), "../../.env") });
import { httpRequest } from "./src/lib/http.js";

async function testInfisical() {
  const INFISICAL_URL = "https://app.infisical.com";
  const clientId = process.env.INFISICAL_CLIENT_ID;
  const clientSecret = process.env.INFISICAL_CLIENT_SECRET;
  
  try {
    const res = await httpRequest(`${INFISICAL_URL}/api/v1/auth/universal-auth/login`, {
      method: "POST",
      body: {
        clientId,
        clientSecret,
      },
    });
    console.log("Login v3 response:", res.data);
  } catch (e) {
    console.log("Login v3 failed:", (e as any).message);
  }
}

testInfisical();
