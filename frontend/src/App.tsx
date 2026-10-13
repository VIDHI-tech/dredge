import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import AuthPage from './pages/AuthPage'; 
import Dashboard from './pages/Dashboard';
import Ingestion from './pages/Ingestion';
import GraphViewer from './pages/GraphViewer';
import NlpQuery from './pages/NlpQuery';
import Landing from './pages';
import type { ReactNode } from 'react';
// import DataAnalyst from './pages/DataAnalyst';

const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  return <>{children}</>;
};

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="ingestion" element={<Ingestion />} />
        <Route path="graph" element={<GraphViewer />} />
        <Route path="nlp" element={<NlpQuery />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AppRoutes />
      </Router>
    </AuthProvider>
  );
}

export default App;