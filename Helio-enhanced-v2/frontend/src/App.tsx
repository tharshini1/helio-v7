import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import CommandPalette from "./components/CommandPalette";
import Pulse from "./components/Pulse";
import { Search, Moon, Sun, Bell } from "lucide-react";
import Dashboard from "./pages/Dashboard";
import Appointments from "./pages/Appointments";
import Doctors from "./pages/Doctors";
import Beds from "./pages/Beds";
import Diagnostics from "./pages/Diagnostics";
import Discharge from "./pages/Discharge";
import Agents from "./pages/Agents";
import Audit from "./pages/Audit";
import PatientPortal from "./pages/PatientPortal";
import EmergencyNurse from "./components/EmergencyNurse";
import EmergencyDoctor from "./components/EmergencyDoctor";
import { API_BASE } from "./config";

type Page =
  | "Dashboard"
  | "Appointments"
  | "Doctors"
  | "Beds"
  | "Diagnostics"
  | "Discharge"
  | "Agents"
  | "Audit";

type Role = "Doctor" | "Nurse" | "Admin" | "Patient";

type User = {
  name: string;
  email: string;
  role: Role;
  patient_id?: number;
};

function App() {
  const [showSplash, setShowSplash] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  const [user, setUser] = useState<User | null>(null);

  const [activePage, setActivePage] = useState<Page>("Dashboard");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem("helio_theme") === "dark");

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("helio_theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginMode, setLoginMode] = useState<"staff" | "patient">("staff");
  const [patientCode, setPatientCode] = useState("");
  const [patientName, setPatientName] = useState("");
  // Patient sign-in: email/phone + password (default) or Patient ID + name.
  const [patientMethod, setPatientMethod] = useState<"account" | "id">("account");
  const [patientIdentifier, setPatientIdentifier] = useState("");
  const [patientPassword, setPatientPassword] = useState("");

  // New patient registration page.
  const [authView, setAuthView] = useState<"login" | "register">("login");
  const [regName, setRegName] = useState("");
  const [regIdentifier, setRegIdentifier] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirm, setRegConfirm] = useState("");
  const [showRegPassword, setShowRegPassword] = useState(false);


  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSplash(false);
    }, 1800);

    return () => clearTimeout(timer);
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");

    if (loginMode === "patient") {
      const byAccount = patientMethod === "account";

      if (byAccount ? !patientIdentifier.trim() || !patientPassword : !patientCode.trim() || !patientName.trim()) {
        setLoginError(
          byAccount
            ? "Please enter your email or phone number and password."
            : "Please enter your Patient ID and name.",
        );
        return;
      }

      setLoggingIn(true);
      try {
        const response = await fetch(`${API_BASE}/api/auth/patient-login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            byAccount
              ? { identifier: patientIdentifier.trim(), password: patientPassword }
              : { patient_code: patientCode, name: patientName },
          ),
        });
        if (!response.ok) {
          setLoginError(
            response.status === 401
              ? byAccount
                ? "Incorrect email/phone or password."
                : "Patient ID and name do not match our records."
              : "Could not reach the Helio server. Please try again.",
          );
          return;
        }
        const account: User = await response.json();
        localStorage.removeItem("helio_role");
        localStorage.removeItem("helio_email");
        setUser(account);
        setIsAuthenticated(true);
      } catch {
        setLoginError("Could not reach the Helio server. Please try again.");
      } finally {
        setLoggingIn(false);
      }
      return;
    }

    if (!loginEmail || !loginPassword) {
      setLoginError("Please enter your email and password.");
      return;
    }

    setLoggingIn(true);

    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });

      if (!response.ok) {
        setLoginError(
          response.status === 401
            ? "This email or password is not authorised for Helio."
            : "Could not reach the Helio server. Please try again.",
        );
        return;
      }

      const account: User = await response.json();

      setUser(account);
      localStorage.setItem("helio_role", account.role);
      localStorage.setItem("helio_email", account.email);
      setIsAuthenticated(true);
      setActivePage("Dashboard");
    } catch {
      setLoginError("Could not reach the Helio server. Please try again.");
    } finally {
      setLoggingIn(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");

    if (!regName.trim() || !regIdentifier.trim() || !regPassword) {
      setLoginError("Please fill in your name, email or phone number, and a password.");
      return;
    }
    if (regPassword.length < 6) {
      setLoginError("Password must be at least 6 characters.");
      return;
    }
    if (regPassword !== regConfirm) {
      setLoginError("The two passwords do not match.");
      return;
    }

    setLoggingIn(true);
    try {
      const response = await fetch(`${API_BASE}/api/auth/patient-register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: regName.trim(),
          identifier: regIdentifier.trim(),
          password: regPassword,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setLoginError(
          typeof data.detail === "string"
            ? data.detail
            : "Could not create your account. Please try again.",
        );
        return;
      }
      // Registered: sign the new patient straight in.
      localStorage.removeItem("helio_role");
      localStorage.removeItem("helio_email");
      setUser(data as User);
      setIsAuthenticated(true);
      setRegName("");
      setRegIdentifier("");
      setRegPassword("");
      setRegConfirm("");
      setAuthView("login");
    } catch {
      setLoginError("Could not reach the Helio server. Please try again.");
    } finally {
      setLoggingIn(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("helio_role");
    localStorage.removeItem("helio_email");
    setPatientCode("");
    setPatientName("");
    setPatientIdentifier("");
    setPatientPassword("");
    setAuthView("login");
    setIsAuthenticated(false);
    setUser(null);
    setLoginEmail("");
    setLoginPassword("");
    setLoginError("");
    setActivePage("Dashboard");
  };

  /* ---------------- SPLASH SCREEN ---------------- */

  if (showSplash) {
    return (
      <div className="helio-splash">
        <Pulse wide />
        <h1>Helio</h1>
        <p>Waking the care agents</p>
      </div>
    );
  }

  /* ---------------- LOGIN / REGISTER ---------------- */

  if (!isAuthenticated && authView === "register") {
    return (
      <div className="auth-page">
        <div className="auth-art">
          <Pulse wide />
          <h2>Your care, one sign-in away.</h2>
          <p>Create a patient account to book appointments and see your discharge summary.</p>
        </div>
        <div className="auth-card">
          <div className="auth-brand">
            <h1>Helio</h1>
            <p>Autonomous Hospital Operations</p>
          </div>

          <div className="auth-heading">
            <h2>Create patient account</h2>
            <p>Register with your email or phone number</p>
          </div>

          <form onSubmit={handleRegister} className="auth-form" noValidate>
            <label htmlFor="reg-name">Full name</label>
            <input
              id="reg-name"
              type="text"
              placeholder="Your full name"
              autoComplete="name"
              value={regName}
              onChange={(e) => setRegName(e.target.value)}
            />

            <label htmlFor="reg-identifier">Email or phone number</label>
            <input
              id="reg-identifier"
              type="text"
              inputMode="email"
              placeholder="you@example.com or +91 98765 43210"
              autoComplete="username"
              value={regIdentifier}
              onChange={(e) => setRegIdentifier(e.target.value)}
            />

            <label htmlFor="reg-password">Password</label>
            <input
              id="reg-password"
              type={showRegPassword ? "text" : "password"}
              placeholder="At least 6 characters"
              autoComplete="new-password"
              value={regPassword}
              onChange={(e) => setRegPassword(e.target.value)}
            />

            <label htmlFor="reg-confirm">Confirm password</label>
            <input
              id="reg-confirm"
              type={showRegPassword ? "text" : "password"}
              placeholder="Re-enter your password"
              autoComplete="new-password"
              value={regConfirm}
              onChange={(e) => setRegConfirm(e.target.value)}
            />

            <label className="auth-check">
              <input
                type="checkbox"
                checked={showRegPassword}
                onChange={(e) => setShowRegPassword(e.target.checked)}
              />
              Show passwords
            </label>

            {loginError && (
              <p className="auth-error" role="alert">
                {loginError}
              </p>
            )}

            <button type="submit" className="auth-button" disabled={loggingIn}>
              {loggingIn ? "Creating account..." : "Create account"}
            </button>
          </form>

          <p className="auth-switch">
            Already registered?{" "}
            <button type="button" onClick={() => { setAuthView("login"); setLoginMode("patient"); setLoginError(""); }}>
              Sign in
            </button>
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="auth-page">
        <div className="auth-art">
          <Pulse wide />
          <h2>Every bed, every hand-off, one steady rhythm.</h2>
          <p>Agents triage and schedule. Clinicians make the final call.</p>
        </div>
        <div className="auth-card">
          <div className="auth-brand">
            <h1>Helio</h1>
            <p>Autonomous Hospital Operations</p>
          </div>

          <div className="auth-heading">
            <h2>Welcome back</h2>
            <p>Sign in to continue to Helio</p>
          </div>

          <div className="auth-tabs">
            <button type="button" className={loginMode === "staff" ? "active" : ""}
              onClick={() => { setLoginMode("staff"); setLoginError(""); }}>Staff</button>
            <button type="button" className={loginMode === "patient" ? "active" : ""}
              onClick={() => { setLoginMode("patient"); setLoginError(""); }}>Patient</button>
          </div>

          <form onSubmit={handleLogin} className="auth-form">
            {loginMode === "staff" ? (
              <>
                <label>Email</label>
                <input
                  type="email"
                  placeholder="Enter your email"
                  autoComplete="username"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                />

                <label>Password</label>
                <input
                  type="password"
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                />
              </>
            ) : (
              patientMethod === "account" ? (
                <>
                  <label>Email or phone number</label>
                  <input
                    type="text"
                    placeholder="you@example.com or phone number"
                    autoComplete="username"
                    value={patientIdentifier}
                    onChange={(e) => setPatientIdentifier(e.target.value)}
                  />

                  <label>Password</label>
                  <input
                    type="password"
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    value={patientPassword}
                    onChange={(e) => setPatientPassword(e.target.value)}
                  />
                </>
              ) : (
                <>
                  <label>Patient ID</label>
                  <input
                    type="text"
                    placeholder="e.g. P003"
                    value={patientCode}
                    onChange={(e) => setPatientCode(e.target.value)}
                  />

                  <label>Full name</label>
                  <input
                    type="text"
                    placeholder="Name as registered"
                    value={patientName}
                    onChange={(e) => setPatientName(e.target.value)}
                  />
                </>
              )
            )}

            {loginError && (
              <p className="auth-error" role="alert">
                {loginError}
              </p>
            )}

            <button type="submit" className="auth-button" disabled={loggingIn}>
              {loggingIn ? "Signing in..." : "Login"}
            </button>
          </form>

          {loginMode === "patient" && (
            <p className="auth-switch">
              <button
                type="button"
                onClick={() => {
                  setPatientMethod(patientMethod === "account" ? "id" : "account");
                  setLoginError("");
                }}
              >
                {patientMethod === "account" ? "Sign in with Patient ID instead" : "Sign in with email or phone"}
              </button>
              <br />
              New patient?{" "}
              <button type="button" onClick={() => { setAuthView("register"); setLoginError(""); }}>
                Create an account
              </button>
            </p>
          )}
        </div>
      </div>
    );
  }

  if (user?.role === "Patient" && user.patient_id) {
    return <PatientPortal patientId={user.patient_id} onLogout={handleLogout} />;
  }

  /* ---------------- MAIN APPLICATION ---------------- */

  return (
    <div className="app-shell">
      {user?.role === "Doctor" && <EmergencyDoctor email={user.email} />}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onGo={(pg) => setActivePage(pg)}
        onToggleTheme={() => setDark((d) => !d)}
        onLogout={handleLogout}
      />
      <Sidebar
        activePage={activePage}
        onPageChange={setActivePage}
      />

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="breadcrumb">Helio / {activePage}</p>
            <h2>{activePage}</h2>
          </div>

          <div className="topbar-right">
            {user?.role === "Nurse" && <EmergencyNurse email={user.email} />}
            <button type="button" className="ghost-button search-trigger" onClick={() => setPaletteOpen(true)}>
              <Search size={16} />
              <span>Search</span>
              <kbd>Ctrl K</kbd>
            </button>
            <button type="button" className="notification-button" aria-label="Toggle theme" onClick={() => setDark((d) => !d)}>
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button type="button" className="notification-button" aria-label="Notifications">
              <Bell size={18} />
            </button>

            <div className="user-profile">
              <div className="user-avatar">
                {user?.name?.charAt(0).toUpperCase() || "H"}
              </div>

              <div>
                <strong>{user?.name || "Healthcare Staff"}</strong>
                <span>{user?.role || "Administrator"}</span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="logout-button"
            >
              Logout
            </button>
          </div>
        </header>
        <section className="page-container" key={activePage}>
        
          {activePage === "Dashboard" ? (
            <Dashboard />
          ) : activePage === "Appointments" ? (
            <Appointments role={user?.role} email={user?.email} />
          ) : activePage === "Doctors" ? (
            <Doctors />
          ) : activePage === "Beds" ? (
            <Beds />
          ) : activePage === "Diagnostics" ? (
            <Diagnostics role={user?.role} email={user?.email} />
          ) : activePage === "Discharge" ? (
            <Discharge />
          ) : activePage === "Agents" ? (
            <Agents />
          ) : activePage === "Audit" ? (
            <Audit />
          ) : (
            <div className="empty-page">
              <div className="empty-icon">✦</div>

              <h3>{activePage}</h3>

              <p>
                This module will be connected to the Helio backend
                in the next step.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;