import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // An effect that returns a value by accident (an arrow with an expression body) makes
      // React call that value as a cleanup; require block bodies for effects.
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='useEffect'] > ArrowFunctionExpression[expression=true]",
          message: "Give effects a block body: an expression body returns its value as the cleanup.",
        },
      ],
    },
  },
);
