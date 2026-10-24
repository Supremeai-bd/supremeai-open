// বাংলা মন্তব্য: ESLint v9 Flat Config ফরম্যাটে কনফিগারেশন করা হলো যাতে out/ ও dist/ ফোল্ডার লিন্টিং থেকে বাদ যায়
import typescriptEslint from "@typescript-eslint/eslint-plugin";
import typescriptParser from "@typescript-eslint/parser";

export default [
  {
    ignores: ["out/", "dist/", "node_modules/", "test/__mocks__/"],
  },
  {
    files: ["src/**/*.ts"],
    plugins: {
      "@typescript-eslint": typescriptEslint,
    },
    languageOptions: {
      parser: typescriptParser,
      parserOptions: {
        project: "./tsconfig.json",
      },
    },
    rules: {
      "semi": ["error", "always"],
      "quotes": ["error", "single"],
      "no-console": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-explicit-any": "off"
    },
  },
];
