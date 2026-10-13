import assert from "node:assert/strict";
import { getServiceDescriptors, serviceDescriptors } from "./src/service-circles.js";

assert.ok(serviceDescriptors.length >= 10);
assert.equal(new Set(serviceDescriptors.map((service) => service.provider)).size, serviceDescriptors.length);
assert.ok(serviceDescriptors.every((service) => service.requiredEnv.length > 0));
assert.ok(getServiceDescriptors().every((service) => typeof service.configured === "boolean"));
console.log(`Service circle metadata passed for ${serviceDescriptors.length} services`);
