import { env } from "../../lib/env.js";
import { initializeApp, cert, App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

let app: App | null = null;

function getFirebaseApp() {
  if (app) return app;

  const saJson = env.firebase.serviceAccountJson;
  if (!saJson) {
    throw new Error("Missing FIREBASE_SERVICE_ACCOUNT_JSON in env.");
  }

  let serviceAccount;
  try {
    serviceAccount = JSON.parse(saJson);
  } catch (e) {
    throw new Error("Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON.");
  }

  app = initializeApp({
    credential: cert(serviceAccount),
  });

  return app;
}

export async function getAuthStatus(): Promise<unknown> {
  const firebaseApp = getFirebaseApp();
  try {
    const listUsersResult = await getAuth(firebaseApp).listUsers(1);
    return {
      status: "healthy",
      sampleUsers: listUsersResult.users.length,
      projectId: firebaseApp.options.projectId || "unknown"
    };
  } catch (e) {
    throw new Error(`Firebase Auth Error: ${(e as Error).message}`);
  }
}

export async function getHostingStatus(): Promise<unknown> {
  const firebaseApp = getFirebaseApp();
  return {
    status: "healthy",
    projectId: firebaseApp.options.projectId || "unknown",
    message: "Firebase Admin SDK initialized successfully."
  };
}
