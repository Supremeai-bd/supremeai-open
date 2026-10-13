/**
 * Noise Filter + Token Budget — умный сбор открытого кода без расхода токенов.
 *
 * Пропускаем: сборки, lock-файлы, бинарники, большие файлы, тест-фикстуры.
 * Приоритезируем: исходники, хуки, компоненты, конфиги, README.
 */

export interface FileDecision {
  shouldScrape: boolean;
  priority: number;
  reason: string;
}

export interface SourceBudget {
  maxFilesPerRepo: number;
  maxTokensPerFile: number;
  maxTotalTokens: number;
}

export const DEFAULT_BUDGET: SourceBudget = {
  maxFilesPerRepo: 25,
  maxTokensPerFile: 4000,
  maxTotalTokens: 60_000,
};

const SKIP_PATTERNS: RegExp[] = [
  /(^|\/)dist\//, /(^|\/)build\//, /(^|\/)node_modules\//, /(^|\/)\.next\//,
  /(^|\/)\.nuxt\//, /(^|\/)coverage\//, /(^|\/)\.git\//, /(^|\/)vendor\//,
  /package-lock\.json$/, /yarn\.lock$/, /pnpm-lock\.yaml$/, /npm-shrinkwrap\.json$/,
  /\.(png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|eot|otf|mp4|webm|mp3|wav|pdf|zip|gz|tgz)$/i,
  /\.(min\.js|min\.css|bundle\.js|bundle\.css|map)$/,
  /__snapshots__\//, /test.*fixtures?\//, /fixtures?\//,
  /\.(lock|sum|sig|asc)$/, /\.editorconfig$/, /\.gitignore$/, /\.gitattributes$/,
  /CHANGELOG\.md$/, /\.npmrc$/, /\.yarnrc$/, /Dockerfile$/, /docker-compose.*\.ya?ml$/,
];

const PRIORITY_PATTERNS: RegExp[] = [
  /\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|kt|swift|c|h)$/,
  /(^|\/)hooks?\//, /(^|\/)components?\//, /(^|\/)utils?\//, /(^|\/)lib\//,
  /(^|\/)services\//, /(^|\/)core\//, /(^|\/)src\//,
  /(^|\/)config\//, /\.config\.(ts|js|mjs|json)$/, /tsconfig.*\.json$/, /vite\.config/, /next\.config/, /tailwind\.config/,
  /README\.md$/, /CONTRIBUTING\.md$/, /LICENSE/,
];

export function decideFile(path: string, sizeBytes: number): FileDecision {
  const p = path.replace(/\\/g, "/");
  if (SKIP_PATTERNS.some((re) => re.test(p))) {
    return { shouldScrape: false, priority: 0, reason: `Noise pattern: ${path}` };
  }
  if (sizeBytes > 200_000) {
    return { shouldScrape: false, priority: 0, reason: `Too large (${sizeBytes} bytes): ${path}` };
  }
  const priority = PRIORITY_PATTERNS.filter((re) => re.test(p)).length;
  return { shouldScrape: true, priority, reason: `Priority ${priority}` };
}

export function estimateTokens(text: string): number {
  // ~4 chars per token (English+code average) — cheap conservative estimate.
  return Math.max(1, Math.ceil(text.length / 4));
}

export class TokenBudget {
  used = 0;
  constructor(private readonly budget: SourceBudget = DEFAULT_BUDGET) {}

  canAdd(fileTokens: number): boolean {
    if (this.used + fileTokens > this.budget.maxTotalTokens) return false;
    return true;
  }

  add(fileTokens: number): void {
    this.used += fileTokens;
  }

  get remaining(): number {
    return Math.max(0, this.budget.maxTotalTokens - this.used);
  }
}