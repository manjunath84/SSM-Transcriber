import { useEffect } from "react";
import {
  Navigate,
  Route,
  Routes,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { beginLogin, completeLogin, getIdToken } from "./auth";
import Dashboard from "./components/Dashboard";
import TranscriptViewer from "./components/TranscriptViewer";

function Landing() {
  return (
    <main>
      <h1>SSM Transcriber</h1>
      <button type="button" onClick={() => void beginLogin()}>
        Sign in with Google
      </button>
    </main>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getIdToken()) {
    return <Landing />;
  }
  return <>{children}</>;
}

function Callback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const code = params.get("code");

  useEffect(() => {
    if (!code) return;
    completeLogin(code)
      .then(() => navigate("/", { replace: true }))
      .catch(() => navigate("/", { replace: true }));
  }, [code, navigate]);

  if (!code) return <Navigate to="/" replace />;
  return <p>Signing you in…</p>;
}

function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        }
      />
      <Route path="/callback" element={<Callback />} />
      <Route
        path="/t/:id"
        element={
          <RequireAuth>
            <TranscriptViewer />
          </RequireAuth>
        }
      />
    </Routes>
  );
}

export default App;
