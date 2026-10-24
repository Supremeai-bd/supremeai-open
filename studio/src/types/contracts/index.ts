// বাংলা মন্তব্য: Universal Zero-Complexity Interface — shared contract barrel।
export * from './connection-contract';
export * from './capability-contract';
export * from './execution-mode';
export {
  type UserCapability,
  type AccessContext,
  type UnavailableCapability,
  type AddIntent,
  ADD_INTENTS,
  capabilityFromModule,
  explainUnavailable,
} from './capability';
