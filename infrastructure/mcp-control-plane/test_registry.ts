import { listResources, getResourceStatus } from "./src/registry/resource.registry.js";

async function main() {
  console.log("Listing resources...");
  const resources = await listResources();
  console.log(JSON.stringify(resources, null, 2));

  console.log("\nTesting status for first resource...");
  if (resources.length > 0) {
    const status = await getResourceStatus(resources[0].id);
    console.log(`Status for ${resources[0].id}: ${status}`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
