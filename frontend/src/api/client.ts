import axios from 'axios';

// Vite proxies API requests to the local gateway during development.
const api = axios.create({
    baseURL: '/api',
});

// Request interceptor to add the auth token to every request
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export default api;
