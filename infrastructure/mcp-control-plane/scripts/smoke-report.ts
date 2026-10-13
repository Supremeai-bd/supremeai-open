import { getServiceDescriptors } from "../src/service-circles.js";

const services = getServiceDescriptors().map((service) => ({
  provider: service.provider,
  circle: service.circle,
  configured: service.configured,
  status: service.configured ? "not_checked" : "not_configured",
  requiredEnv: service.requiredEnv,
}));

const report = {
  generatedAt: new Date().toISOString(),
  mode: "configuration-only",
  summary: {
    total: services.length,
    configured: services.filter((service) => service.configured).length,
    notConfigured: services.filter((service) => !service.configured).length,
  },
  services,
};

console.log(JSON.stringify(report, null, 2));
