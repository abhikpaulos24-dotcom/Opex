import { createContext, useContext, useState, type ReactNode } from "react";

// Live data refreshes every few seconds. People who need time to read (or use a screen reader)
// can pause it - WCAG 2.2.2 "Pause, stop, hide".
const LiveContext = createContext<{ paused: boolean; setPaused: (paused: boolean) => void }>({
  paused: false,
  setPaused: () => undefined,
});

export function LiveProvider({ children }: { children: ReactNode }) {
  const [paused, setPaused] = useState(false);
  return <LiveContext.Provider value={{ paused, setPaused }}>{children}</LiveContext.Provider>;
}

export function useLive() {
  return useContext(LiveContext);
}

/** Refetch interval for live queries: `ms`, or never while paused. */
export function useRefresh(ms: number): number | false {
  return useLive().paused ? false : ms;
}
