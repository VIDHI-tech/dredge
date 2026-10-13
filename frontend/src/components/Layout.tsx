import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Database, Upload, Network, MessageSquare, LogOut } from 'lucide-react';
import dredge from '../assets/dredge.png';

const Layout = () => {
    const { user, currentBucket, buckets, setBucket, logout } = useAuth();
    const navigate = useNavigate();
    const showSidebar = Boolean(currentBucket);

    const handleLogout = () => {
        logout();
        navigate('/auth');
    };

    return (
        <div className="app-container">
            {showSidebar && (
                <nav className="sidebar">
                    <div className="sidebar-header">
                        <div >
                           <img src={dredge} width={35} height={35} alt="Dredge" />
                        </div>
                        <span>Dredge</span>
                    </div>

                    <div className="nav-links">
                        <NavLink
                            to="/dashboard"
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                            end
                        >
                            <Database size={20} />
                            Dashboard
                        </NavLink>
                        <NavLink
                            to="/dashboard/ingestion"
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                        >
                            <Upload size={20} />
                            Ingestion
                        </NavLink>
                        <NavLink
                            to="/dashboard/graph"
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                        >
                            <Network size={20} />
                            Graph Viewer
                        </NavLink>
                        <NavLink
                            to="/dashboard/nlp"
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                        >
                            <MessageSquare size={20} />
                            NLP Query
                        </NavLink>
                    </div>

                    <div className="user-section">
                        <div className="bucket-selector">
                            <label htmlFor="bucket-select">Active Bucket</label>
                            <select
                                id="bucket-select"
                                className="input-field"
                                value={currentBucket || ''}
                                onChange={(e) => setBucket(e.target.value)}
                            >
                                <option value="" disabled>Select a bucket...</option>
                                {buckets.map(b => (
                                    <option key={b} value={b}>{b}</option>
                                ))}
                            </select>
                        </div>

                        <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '160px' }}>
                                {user?.email}
                            </span>
                            <button
                                onClick={handleLogout}
                                className="btn btn-secondary"
                                style={{ padding: '0.5rem', border: 'none' }}
                                title="Logout"
                            >
                                <LogOut size={18} />
                            </button>
                        </div>
                    </div>
                </nav>
            )}

            <main
                className="main-content"
                style={showSidebar ? undefined : { marginLeft: 0, width: '100%' }}
            >
                <div className="main-content-inner">
                    <Outlet />
                </div>
            </main>
        </div>
    );
};

export default Layout;
