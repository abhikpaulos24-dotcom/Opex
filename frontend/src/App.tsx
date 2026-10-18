import { useEffect } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useSession } from "./lib/session";
import Actions from "./pages/Actions";
import Copilot from "./pages/Copilot";
import Learning from "./pages/Learning";
import Login from "./pages/Login";
import Machine from "./pages/machine";
import Overview from "./pages/Overview";
import Settings from "./pages/Settings";
import Simulation from "./pages/simulation";

const TITLES: Record<string, string> = {
  "/": "Overview", "/actions": "Actions", "/copilot": "Ask OpEx", "/simulation": "5-year simulation",
  "/learning": "Learning log", "/settings": "Settings", "/login": "Sign in",
};

export default function App() {
  const { user } = useSession();
  const location = useLocation();

  // Tell screen-reader users the page changed and move focus to the new content.
  useEffect(() => {
    const name = TITLES[location.pathname] ?? (location.pathname.startsWith("/machines/") ? location.pathname.split("/")[2] : "OpEx");
    document.title = `${name} · OpEx`;
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [location.pathname]);

  if (user === undefined) return <div style={{ padding: 24 }}><Loading label="Opening OpEx" /></div>;
  if (user === null) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/machines/:id" element={<Machine />} />
        <Route path="/actions" element={<Actions />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="/simulation" element={<Simulation />} />
        <Route path="/learning" element={<Learning />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<div className="card"><h1>That page isn't here</h1><p className="muted">The link may be old, or the machine may have been renamed.</p><Link className="btn primary" to="/">Back to the overview</Link></div>} />
      </Routes>
    </Layout>
  );
}
