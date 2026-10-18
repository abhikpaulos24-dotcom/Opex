import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";

export type Prefs = {
  theme: "system" | "light" | "dark" | "contrast";
  text: "m" | "l" | "xl";
  font: "atkinson" | "lexend" | "opendyslexic";
  motion: "full" | "reduce";
  spacing: "normal" | "wide";
  simple: boolean;       // plain-language explanations
  language: string;      // AI answers + read-aloud voice
  voiceRate: number;
  focus: boolean;        // hide secondary panels
};

export type User = {
  id: string; email: string; full_name: string; role: string; role_label: string;
  permissions: string[]; preferences: Partial<Prefs>;
};

export type AppConfig = {
  demo_mode: boolean; google_client_id: string | null; gemini: boolean; gemini_model: string | null; bigquery: boolean;
  cloud_storage: boolean; pubsub: boolean; database: string; live_speed: number;
  demo_accounts: { email: string; full_name: string; role: string }[];
  demo_password: string | null;
};

const DEFAULT_PREFS: Prefs = {
  theme: "light", text: "m", font: "atkinson", motion: "full", spacing: "normal",
  simple: false, language: "en", voiceRate: 1, focus: false,
};

type Session = {
  user: User | null | undefined;          // undefined = still checking
  config: AppConfig | null;
  prefs: Prefs;
  setPref: <K extends keyof Prefs>(key: K, value: Prefs[K]) => void;
  signIn: (user: User) => void;
  signOut: () => Promise<void>;
  can: (permission: string) => boolean;
};

const SessionContext = createContext<Session | null>(null);

const THEME_RESET = "opex-light-default";
let themeJustReset = false;
/** Earlier versions followed the device and showed dark. Move everyone to light once; their later choice sticks. */
function resetTheme(prefs: Prefs): Prefs {
  try {
    if (localStorage.getItem(THEME_RESET)) return prefs;
    localStorage.setItem(THEME_RESET, "1");
  } catch { /* ignore */ }
  themeJustReset = true;
  return { ...prefs, theme: "light" };
}

/** Saved account preferences, except the theme on the one visit where we reset it to light. */
function withServer(p: Prefs, saved: Partial<Prefs>): Prefs {
  return { ...p, ...saved, ...(themeJustReset ? { theme: "light" as const } : {}) };
}

function loadLocalPrefs(): Prefs {
  try {
    return resetTheme({ ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem("opex-prefs") ?? "{}") });
  } catch {
    return DEFAULT_PREFS;
  }
}

function applyPrefs(prefs: Prefs) {
  const root = document.documentElement;
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = prefs.theme === "system" ? (dark ? "dark" : "light") : prefs.theme;
  root.dataset.text = prefs.text;
  root.dataset.font = prefs.font;
  root.dataset.motion = prefs.motion;
  root.dataset.spacing = prefs.spacing;
  root.lang = prefs.language === "en" ? "en-IN" : prefs.language;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [prefs, setPrefs] = useState<Prefs>(loadLocalPrefs);
  const saveTimer = useRef<number>(undefined);

  useEffect(() => {
    api<AppConfig>("/api/config").then(setConfig).catch(() => setConfig(null));
    api<User>("/api/auth/me")
      .then((me) => {
        setUser(me);
        setPrefs((p) => withServer(p, me.preferences));
        // Save the light reset to the account too, so a saved "dark" can't bring it back next visit.
        if (themeJustReset) api("/api/auth/me/preferences", { method: "PUT", body: { preferences: { ...me.preferences, theme: "light" } } }).catch(() => undefined);
      })
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    applyPrefs(prefs);
    try {
      localStorage.setItem("opex-prefs", JSON.stringify(prefs));
    } catch {
      /* private mode - preferences just won't persist */
    }
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onChange = () => applyPrefs(prefs);
    media?.addEventListener("change", onChange);
    return () => media?.removeEventListener("change", onChange);
  }, [prefs]);

  const setPref = useCallback(<K extends keyof Prefs>(key: K, value: Prefs[K]) => {
    setPrefs((current) => {
      const next = { ...current, [key]: value };
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => {
        api("/api/auth/me/preferences", { method: "PUT", body: { preferences: next } }).catch(() => undefined);
      }, 800);
      return next;
    });
  }, []);

  const value = useMemo<Session>(() => ({
    user, config, prefs, setPref,
    signIn: (u) => {
      setUser(u);
      setPrefs((p) => withServer(p, u.preferences));
    },
    signOut: async () => {
      await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
      setUser(null);
    },
    can: (permission) => !!user?.permissions.includes(permission),
  }), [user, config, prefs, setPref]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}
