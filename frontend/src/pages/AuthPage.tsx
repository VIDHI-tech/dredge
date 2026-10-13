import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { motion } from 'framer-motion';
import { Lock, Mail } from 'lucide-react';
import dredge from "../assets/dredge.png";
import landingVideo from '../assets/bg.mp4';
import '../App.css';

const AuthPage = () => {
    const [isLogin, setIsLogin] = useState(true);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const { login } = useAuth();
    const navigate = useNavigate();

    const AUTH_PARTICLES = Array.from({ length: 14 }, (_, i) => ({
        id: i,
        style: {
            left: `${Math.random() * 100}%`,
            width: `${Math.random() * 2 + 1}px`,
            height: `${Math.random() * 2 + 1}px`,
            '--drift': `${(Math.random() - 0.5) * 100}px`,
            animationDuration: `${Math.random() * 12 + 10}s`,
            animationDelay: `${Math.random() * -20}s`,
            opacity: Math.random() * 0.4 + 0.08,
        },
    }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const endpoint = isLogin ? '/auth/login' : '/auth/signup';
            const response = await api.post(endpoint, { email, password });
            login(response.data.token, response.data.email, response.data.db_name);
            navigate('/dashboard');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Authentication failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-page">
            <div className="auth-scene">
                {/* Floating particles — same as landing */}
                <div className="auth-particles">
                    {AUTH_PARTICLES.map((p) => (
                        <div key={p.id} className="auth-particle" style={p.style} />
                    ))}
                </div>

                {/* Video panel right (65vw) — same video as landing page */}
                <div className="auth-video-panel desktop-video-only">
                    <video autoPlay muted loop playsInline src={landingVideo} />
                    <div className="auth-gradient-overlay" aria-hidden="true" />
                </div>

                {/* Left content area */}
                <div className="auth-content-area">
                    <div className="auth-card-wrapper">
                        <div className="auth-glass-panel">
                    <span className="auth-card-shine" aria-hidden="true" />

                    <motion.div
                        className="auth-panel-header"
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.5, duration: 0.4 }}
                    >
                        <figure className="lp-logo">
                            <img src={dredge} alt="Dredge" />
                        </figure>
                        <p className="page-subtitle auth-subtitle" style={{ marginBottom: 0 }}>
                            {isLogin ? 'Welcome back — sign in to continue' : 'Create your account to get started'}
                        </p>
                    </motion.div>

                    {error && (
                        <motion.div
                            className="auth-error"
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            transition={{ duration: 0.3 }}
                        >
                            {error}
                        </motion.div>
                    )}

                    <motion.form
                        onSubmit={handleSubmit}
                        initial="hidden"
                        animate="visible"
                        variants={{
                            visible: { transition: { staggerChildren: 0.06, delayChildren: 0.55 } },
                            hidden: {},
                        }}
                    >
                        <motion.div
                            className="form-group auth-form-group"
                            variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
                        >
                            <label>Email</label>
                            <div className="auth-input-wrap">
                                <Mail size={18} className="auth-input-icon" />
                                <input
                                    type="email"
                                    className="input-field auth-input"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    placeholder="hey@example.com"
                                />
                            </div>
                        </motion.div>

                        <motion.div
                            className="form-group auth-form-group"
                            variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
                        >
                            <label>Password</label>
                            <div className="auth-input-wrap">
                                <Lock size={18} className="auth-input-icon" />
                                <input
                                    type="password"
                                    className="input-field auth-input"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    minLength={6}
                                    placeholder="At least 6 characters"
                                />
                            </div>
                        </motion.div>

                        <motion.div variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}>
                            <button
                                type="submit"
                                className="btn btn-primary auth-submit-btn"
                                style={{ width: '100%', marginTop: '0.5rem', padding: '0.85rem' }}
                                disabled={loading}
                            >
                                {loading ? (
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <span className="loading-dot" /> Processing...
                                    </span>
                                ) : isLogin ? 'Sign In' : 'Create Account'}
                            </button>
                        </motion.div>
                    </motion.form>

                    <motion.div
                        className="auth-footer"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.85, duration: 0.4 }}
                    >
                        <p style={{ margin: 0 }}>
                            {isLogin ? "Don't have an account? " : "Already have an account? "}
                            <button
                                type="button"
                                className="auth-toggle-btn"
                                onClick={() => { setIsLogin(!isLogin); setError(''); }}
                            >
                                {isLogin ? 'Sign Up' : 'Sign In'}
                            </button>
                        </p>
                    </motion.div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AuthPage;
