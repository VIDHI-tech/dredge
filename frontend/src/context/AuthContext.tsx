import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import api from '../api/client';

export interface UserProfile {
    user_id: string;
    email: string;
    db_name: string;
    buckets: string[];
    merged_buckets: string[];
}

interface AuthContextType {
    token: string | null;
    user: UserProfile | null;
    currentBucket: string | null;
    buckets: string[];
    mergedBuckets: string[];
    bucketCounts: Record<string, number>;
    login: (token: string, email: string, db_name: string) => void;
    logout: () => void;
    setBucket: (bucket: string) => void;
    refreshBuckets: () => Promise<void>;
    mergeBuckets: (bucketsToMerge: string[]) => Promise<void>;
    unmergeBucket: (mergedName: string) => Promise<void>;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
    const [user, setUser] = useState<UserProfile | null>(null);
    const [currentBucket, setCurrentBucket] = useState<string | null>(localStorage.getItem('currentBucket'));
    const [buckets, setBuckets] = useState<string[]>([]);
    const [mergedBuckets, setMergedBuckets] = useState<string[]>([]);
    const [bucketCounts, setBucketCounts] = useState<Record<string, number>>({});

    useEffect(() => {
        if (token && !user) {
            api.get('/auth/me')
                .then(res => {
                    setUser(res.data);
                    setBuckets(res.data.buckets || []);
                    setMergedBuckets(res.data.merged_buckets || []);
                })
                .catch(() => {
                    logout();
                });
        }
    }, [token]);

    const refreshBuckets = async () => {
        try {
            const res = await api.get('/auth/buckets');
            setBuckets(res.data.buckets || []);
            setMergedBuckets(res.data.merged_buckets || []);
            setBucketCounts(res.data.counts || {});
        } catch (err) {
            console.error('Failed to refresh buckets', err);
        }
    };

    const mergeBuckets = async (bucketsToMerge: string[]) => {
        await api.post('/auth/buckets/merge', { buckets: bucketsToMerge });
        await refreshBuckets();
    };

    const unmergeBucket = async (mergedName: string) => {
        await api.post('/auth/buckets/unmerge', { merged_name: mergedName });
        if (currentBucket === mergedName) setCurrentBucket(null);
        await refreshBuckets();
    };

    const login = (newToken: string, email: string, db_name: string) => {
        setToken(newToken);
        setUser({ user_id: '', email, db_name, buckets: [], merged_buckets: [] });
        localStorage.setItem('token', newToken);
        api.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
        api.get('/auth/me').then(res => {
            setUser(res.data);
            setBuckets(res.data.buckets || []);
            setMergedBuckets(res.data.merged_buckets || []);
        });
    };

    const logout = () => {
        setToken(null);
        setUser(null);
        setCurrentBucket(null);
        setBuckets([]);
        setMergedBuckets([]);
        setBucketCounts({});
        localStorage.removeItem('token');
        localStorage.removeItem('currentBucket');
    };

    const setBucket = (bucket: string) => {
        setCurrentBucket(bucket);
        localStorage.setItem('currentBucket', bucket);
    };

    return (
        <AuthContext.Provider value={{
            token,
            user,
            currentBucket,
            buckets,
            mergedBuckets,
            bucketCounts,
            login,
            logout,
            setBucket,
            refreshBuckets,
            mergeBuckets,
            unmergeBucket,
            isAuthenticated: !!token
        }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
