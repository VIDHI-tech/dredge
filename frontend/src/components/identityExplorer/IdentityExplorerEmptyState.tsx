import { Users } from 'lucide-react';
import dredge from '../../assets/dredge.png';

export function IdentityExplorerEmptyState() {
  return (
    <div style={{ position: 'relative', minHeight: '550px' }}>
      <div
        aria-hidden="true"
        style={{
          position: 'absolute', inset: 0, zIndex: 0,
          backgroundImage: `linear-gradient(to bottom, rgba(248, 250, 252, 0.92) 0%, rgba(241, 245, 249, 0.88) 50%, rgba(248, 250, 252, 0.92) 100%), url(${dredge})`,
          backgroundPosition: 'center', backgroundRepeat: 'no-repeat',
          pointerEvents: 'none',
        }}
      />
      <div style={{ textAlign: 'center', padding: '6rem 0', color: 'var(--text-secondary)', position: 'relative', zIndex: 1 }}>
        <Users size={48} style={{ opacity: 0.12, margin: '0 auto 1rem', display: 'block' }} />
        <p>Click &quot;Build Index&quot; to create the identity explorer.</p>
        <p style={{ fontSize: '0.8rem', marginTop: '0.5rem', opacity: 0.6 }}>Browse users alphabetically, explore identity links, and discover connections.</p>
      </div>
    </div>
  );
}
