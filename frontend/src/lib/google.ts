// Google's sign-in button ("Google Identity Services"). It hands us a signed token; the server checks it.
const SCRIPT = "https://accounts.google.com/gsi/client";

type Google = {
  accounts: {
    id: {
      initialize: (options: { client_id: string; callback: (response: { credential: string }) => void }) => void;
      renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
    };
  };
};

let loading: Promise<Google> | null = null;

export function loadGoogle(): Promise<Google> {
  loading ??= new Promise((resolve, reject) => {
    const existing = (window as unknown as { google?: Google }).google;
    if (existing) return resolve(existing);
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () => resolve((window as unknown as { google: Google }).google);
    script.onerror = () => {
      loading = null; // allow a retry after the network comes back
      reject(new Error("Could not reach Google. Check your internet connection and reload."));
    };
    document.head.appendChild(script);
  });
  return loading;
}
