import { Network, Zap, Users } from 'lucide-react';

export interface GraphExplorerLandingPanelProps {
  onSelectSunburst: () => void;
  onSelectIdentity: () => void;
}

/**
 * Default “choose an explorer” hero when no graph mode is active yet.
 */
export function GraphExplorerLandingPanel({ onSelectSunburst, onSelectIdentity }: GraphExplorerLandingPanelProps) {
  return (
    <>
      <style>{`
        @keyframes graphLandingOrbitPanel { 100% { transform: rotate(360deg); } }
        @keyframes graphLandingFloatPanel {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }
        @keyframes graphLandingPulsePanel {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.02); }
        }
        .graph-landing-panel .graph-landing-card-btn { transition: transform 0.2s ease, box-shadow 0.2s ease; }
        .graph-landing-panel .graph-landing-card-btn:hover { transform: translateY(-2px) scale(1.01); }
      `}</style>
      <div
        className="glass-panel graph-landing-panel"
        style={{
          padding: 0,
          overflow: 'hidden',
          borderRadius: 16,
          border: '1px solid var(--glass-border)',
          minHeight: 420,
          position: 'relative',
          background:
            'radial-gradient(ellipse 80% 60% at 50% 40%, rgba(13, 148, 136, 0.12) 0%, transparent 55%), linear-gradient(165deg, var(--bg-card) 0%, var(--bg-page) 45%, rgba(13, 148, 136, 0.06) 100%)',
        }}
      >
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: '-40%',
            background:
              'conic-gradient(from 0deg, transparent, rgba(13, 148, 136, 0.07), transparent 40%, rgba(56, 189, 248, 0.06), transparent 70%)',
            animation: 'graphLandingOrbitPanel 14s linear infinite',
          }}
        />
        <div
          style={{
            position: 'relative',
            zIndex: 1,
            padding: '2.75rem 2rem 3rem',
            textAlign: 'center',
            maxWidth: 720,
            margin: '0 auto',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '1rem',
              marginBottom: '1.25rem',
              animation: 'graphLandingFloatPanel 5s ease-in-out infinite',
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                background: 'var(--primary-light)',
                border: '2px solid rgba(13, 148, 136, 0.35)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(13, 148, 136, 0.15)',
              }}
            >
              <Network size={28} style={{ color: 'var(--primary)' }} />
            </div>
          </div>
          <h2
            style={{
              margin: '0 0 0.5rem',
              fontSize: '1.35rem',
              color: 'var(--primary)',
              fontWeight: 700,
              letterSpacing: '0.02em',
            }}
          >
            Choose an explorer
          </h2>
          <p
            style={{
              margin: '0 auto 2rem',
              color: 'var(--text-secondary)',
              lineHeight: 1.55,
              fontSize: '0.95rem',
              maxWidth: 460,
            }}
          >
            Pick <strong style={{ color: 'var(--text-primary)' }}>Sunburst</strong> for field/value radial drill-down, or{' '}
            <strong style={{ color: 'var(--text-primary)' }}>Identity</strong> for user linkage. Use the tabs above anytime to
            switch.
          </p>
          <div
            style={{
              display: 'flex',
              gap: '1rem',
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            <button
              type="button"
              className="btn btn-primary graph-landing-card-btn"
              style={{
                flex: '1 1 240px',
                maxWidth: 300,
                padding: '1.35rem 1.25rem',
                borderRadius: 14,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '0.65rem',
                fontSize: '0.95rem',
                animation: 'graphLandingPulsePanel 3.5s ease-in-out infinite',
                boxShadow: '0 4px 24px rgba(13, 148, 136, 0.2)',
              }}
              onClick={onSelectSunburst}
            >
              <Zap size={32} style={{ opacity: 0.95 }} />
              <span style={{ fontWeight: 700 }}>Sunburst Explorer</span>
              <span style={{ fontSize: '0.8rem', opacity: 0.9, fontWeight: 400 }}>Radial field & value map</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary graph-landing-card-btn"
              style={{
                flex: '1 1 240px',
                maxWidth: 300,
                padding: '1.35rem 1.25rem',
                borderRadius: 14,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '0.65rem',
                fontSize: '0.95rem',
                borderWidth: 2,
                animation: 'graphLandingPulsePanel 3.5s ease-in-out infinite 0.35s',
                boxShadow: '0 4px 20px rgba(0, 0, 0, 0.06)',
              }}
              onClick={onSelectIdentity}
            >
              <Users size={32} style={{ color: 'var(--primary)' }} />
              <span style={{ fontWeight: 700 }}>Identity Explorer</span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                People & connection graph
              </span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
