/**
 * Auth Callback Page
 * Handles magic link verification and OAuth redirects
 */

import { AlertCircle,CheckCircle,Loader } from 'lucide-react';
import React,{ useEffect,useState } from 'react';
import { useNavigate,useSearchParams } from 'react-router-dom';
import { supabase } from '../lib/auth';

export const AuthCallbackPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // Check for error in URL (failed OAuth)
        const error = searchParams.get('error');
        if (error) {
          setStatus('error');
          setMessage(error === 'access_denied' 
            ? 'You denied the connection request.' 
            : `Error: ${error}`);
          return;
        }

        // Get session from URL params (magic link or OAuth)
        const { data, error: sessionError } = await supabase.auth.getSession();

        if (sessionError || !data.session) {
          setStatus('error');
          setMessage('Authentication failed. Please try again.');
          return;
        }

        setStatus('success');
        setMessage('Redirecting...');

        // Redirect to dashboard after 1 second
        setTimeout(() => {
          navigate('/dashboard');
        }, 1000);
      } catch (err) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : 'Authentication failed');
      }
    };

    handleCallback();
  }, [searchParams, navigate]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-purple-50 to-blue-50">
      <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center space-y-4">
        {status === 'loading' && (
          <>
            <Loader className="w-12 h-12 animate-spin mx-auto text-purple-600" />
            <h1 className="text-2xl font-bold text-gray-900">Verifying...</h1>
            <p className="text-gray-600">Authenticating your account</p>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle className="w-12 h-12 text-green-500 mx-auto" />
            <h1 className="text-2xl font-bold text-gray-900">Welcome!</h1>
            <p className="text-gray-600">Redirecting to dashboard...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <AlertCircle className="w-12 h-12 text-red-500 mx-auto" />
            <h1 className="text-2xl font-bold text-gray-900">Authentication Failed</h1>
            <p className="text-gray-600">{message}</p>
            <button
              onClick={() => navigate('/auth')}
              className="mt-6 px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition font-medium"
            >
              Try Again
            </button>
          </>
        )}
      </div>
    </div>
  );
};
