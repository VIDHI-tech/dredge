import "../App.css";
import { useNavigate } from "react-router-dom";
import dredge from "../assets/dredge.png";
import video from "../assets/bg.mp4";

const PARTICLES = Array.from({ length: 18 }, (_, i) => {
  const size = Math.random() * 2 + 1;
  return {
    id: i,
    style: {
      left: `${Math.random() * 55}%`,
      width: `${size}px`,
      height: `${size}px`,
      "--drift": `${(Math.random() - 0.5) * 120}px`,
      animationDuration: `${Math.random() * 12 + 10}s`,
      animationDelay: `${Math.random() * -20}s`,
      opacity: Math.random() * 0.5 + 0.1,
    },
  };
});

function ArrowIcon() {
  return (
    <svg
      className="lp-arrow"
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
    >
      <path
        d="M2 7h10M8 3l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="lp-page">
      {/* ── Floating particles ──────────────────────────── */}
      <div className="lp-particles">
        {PARTICLES.map((p) => (
          <div key={p.id} className="lp-particle" style={p.style} />
        ))}
      </div>

      {/* ── Main scene ──────────────────────────────────── */}
      <div className="lp-scene">

        {/* Video panel: video + gradient overlay inside for seamless blend */}
        <div className="lp-video-panel desktop-video-only">
          <video autoPlay muted loop playsInline src={video} />
          <div className="lp-gradient-overlay" aria-hidden="true" />
        </div>

        {/* Left: content area */}
        <div className="lp-content-area">

          {/* Glassmorphism card with step-in animation */}
          <div className="lp-glass-card">
            <span className="lp-card-shine" aria-hidden="true" />

            <figure className="lp-logo">
              <img src={dredge} alt="Dredge" />
            </figure>

            <h1 className="lp-headline lp-welcome">Welcome to Dredge</h1>

            <div className="lp-btn-group">
              <button
                type="button"
                className="lp-btn-primary"
                onClick={() => navigate("/auth")}
              >
                Let's Get Started <ArrowIcon />
              </button> 
            </div>

            <div className="lp-card-divider" />

            {/* <p className="lp-footnote">
              Already a admin ? {"  "}
              <Link to="/auth"> Sign in here</Link>
            </p> */}

          </div>
        </div>
      </div>

      {/* ── Scroll hint ─────────────────────────────────── */}
      {/* <div className="lp-scroll-hint">
        <span>Scroll</span>
        <div className="lp-scroll-line" />
      </div> */}
    </div>
  );
}
