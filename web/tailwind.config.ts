import type { Config } from "tailwindcss";

// Colors are CSS variables (src/styles/index.css) so light and dark share one palette.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"),
        surface: token("surface"),
        subtle: token("subtle"),
        line: token("line"),
        "line-strong": token("line-strong"),
        control: token("control"),
        ink: token("ink"),
        muted: token("muted"),
        faint: token("faint"),
        accent: token("accent"),
        "accent-soft": token("accent-soft"),
        "accent-ink": token("accent-ink"),
        ok: token("ok"),
        "ok-soft": token("ok-soft"),
        warn: token("warn"),
        "warn-soft": token("warn-soft"),
        bad: token("bad"),
        "bad-soft": token("bad-soft"),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
        serif: ['"Source Serif 4 Variable"', "Georgia", "serif"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1.125rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        md: ["0.875rem", { lineHeight: "1.375rem" }],
        "2xl": ["1.5rem", { lineHeight: "1.875rem" }],
      },
      borderRadius: {
        DEFAULT: "3px",
        sm: "2px",
        md: "4px",
      },
      boxShadow: {
        pop: "0 2px 6px rgb(0 0 0 / 0.10)",
        dialog: "0 12px 32px -8px rgb(0 0 0 / 0.22)",
      },
      letterSpacing: {
        caps: "0.06em",
      },
    },
  },
  plugins: [],
} satisfies Config;
