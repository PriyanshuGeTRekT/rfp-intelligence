import { useCallback, useEffect, useState } from "react";

import { KEYS, readStored, writeStored } from "./storage";

export type ThemePreference = "system" | "light" | "dark";

function apply(pref: ThemePreference) {
  const dark = pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function useTheme(): [ThemePreference, (p: ThemePreference) => void] {
  const [pref, setPref] = useState<ThemePreference>(() => readStored<ThemePreference>(KEYS.theme, "system"));

  useEffect(() => {
    apply(pref);
    if (pref !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [pref]);

  const update = useCallback((p: ThemePreference) => {
    writeStored(KEYS.theme, p === "system" ? null : p);
    setPref(p);
  }, []);

  return [pref, update];
}
