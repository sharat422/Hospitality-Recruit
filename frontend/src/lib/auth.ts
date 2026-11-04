/**
 * Supabase Auth Configuration & Utilities
 * Handles magic link + social authentication
 */

// Use the shared Supabase client — do NOT create a second instance.
// All auth operations share one client so session state stays consistent.
import { supabase } from '@/lib/supabase';
export { supabase };

export const signUpWithPassword = async (email: string, password: string) => {
  try {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    return { success: true, data };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Sign up failed' };
  }
};

export const signInWithPassword = async (email: string, password: string) => {
  try {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return { success: true, data };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Sign in failed' };
  }
};

/**
 * Authentication Types
 */
export interface AuthUser {
  id: string;
  email: string;
  user_metadata?: {
    first_name?: string;
    last_name?: string;
    company_name?: string;
  };
  is_admin?: boolean;
  created_at: string;
}

export interface AuthSession {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
}

/**
 * Magic Link Authentication
 */
export const sendMagicLink = async (email: string) => {
  try {
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) throw error;
    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to send magic link',
    };
  }
};

/**
 * Social Authentication (Google, GitHub, etc)
 */
export const signInWithProvider = async (provider: 'google' | 'github') => {
  try {
    const { error, data } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) throw error;
    return { success: true, data };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : `Failed to sign in with ${provider}`,
    };
  }
};

/**
 * Sign Out
 */
export const signOut = async () => {
  try {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to sign out',
    };
  }
};

/**
 * Get Current Session
 */
export const getCurrentSession = async (): Promise<AuthSession> => {
  try {
    const { data, error } = await supabase.auth.getSession();

    if (error) throw error;

    const session = data.session;
    return {
      user: session?.user as AuthUser | null,
      isLoading: false,
      isAuthenticated: !!session,
      error: null,
    };
  } catch (error) {
    return {
      user: null,
      isLoading: false,
      isAuthenticated: false,
      error: error instanceof Error ? error.message : 'Failed to get session',
    };
  }
};

/**
 * Update User Metadata
 */
export const updateUserMetadata = async (metadata: {
  first_name?: string;
  last_name?: string;
  company_name?: string;
  [key: string]: any;
}) => {
  try {
    const { data, error } = await supabase.auth.updateUser({
      data: metadata,
    });

    if (error) throw error;
    return { success: true, user: data.user as AuthUser };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to update user',
    };
  }
};

/**
 * Subscribe to Auth State Changes
 */
export const onAuthStateChange = (callback: (session: AuthSession) => void) => {
  return supabase.auth.onAuthStateChange(async (_event, session) => {
    if (session) {
      callback({
        user: session.user as AuthUser,
        isLoading: false,
        isAuthenticated: true,
        error: null,
      });
    } else {
      callback({
        user: null,
        isLoading: false,
        isAuthenticated: false,
        error: null,
      });
    }
  });
};

/**
 * API Helper - Call backend with auth token
 */
export const apiCall = async (
  endpoint: string,
  options: RequestInit = {}
) => {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const headers = {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
    ...options.headers,
  };

  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "/api/v1"}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.statusText}`);
  }

  return response.json();
};
