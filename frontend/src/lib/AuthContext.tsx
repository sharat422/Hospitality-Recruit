/**
 * Auth Context for global state management
 * Provides authentication state and methods to all components
 */

import React,{ createContext,useContext,useEffect,useState } from 'react';
import { AuthUser,getCurrentSession,onAuthStateChange } from './auth';

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthContextType>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
    error: null,
  });

  useEffect(() => {
    // Get initial session
    const initSession = async () => {
      const session = await getCurrentSession();
      setState(session);
    };

    initSession();

    // Subscribe to auth changes
    const { data: unsubscribe } = onAuthStateChange((session) => {
      setState(session);
    });

    return () => {
      unsubscribe?.subscription.unsubscribe();
    };
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
