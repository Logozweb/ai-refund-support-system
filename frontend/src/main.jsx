import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

class ErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("UI crash:", error, info?.componentStack); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ maxWidth: 640, margin: "60px auto", fontFamily: "system-ui" }}>
        <h2>Something went wrong in the UI</h2>
        <pre style={{ background: "#fff0f0", padding: 12, whiteSpace: "pre-wrap" }}>{String(this.state.error?.stack || this.state.error)}</pre>
        <button onClick={() => location.reload()}>Reload</button>
      </div>
    );
  }
}
createRoot(document.getElementById("root")).render(<ErrorBoundary><App /></ErrorBoundary>);
