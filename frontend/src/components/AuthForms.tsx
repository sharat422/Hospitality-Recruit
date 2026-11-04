import { CheckCircle,Eye,EyeOff,Loader,Lock,Mail,XCircle } from 'lucide-react';
import React,{ useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { signInWithPassword,signUpWithPassword } from '../lib/auth';

const PASSWORD_RULES = [
  { label: 'At least 8 characters',       test: (p: string) => p.length >= 8 },
  { label: 'One uppercase letter (A–Z)',   test: (p: string) => /[A-Z]/.test(p) },
  { label: 'One lowercase letter (a–z)',   test: (p: string) => /[a-z]/.test(p) },
  { label: 'One number (0–9)',             test: (p: string) => /[0-9]/.test(p) },
  { label: 'One special character (!@#…)', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
];

function PasswordStrength({ password }: { password: string }) {
  if (!password) return null;
  return (
    <ul className="mt-2 space-y-1">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(password);
        return (
          <li key={rule.label} className={`flex items-center gap-2 text-xs ${ok ? 'text-green-600' : 'text-gray-400'}`}>
            {ok ? <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" /> : <XCircle className="w-3.5 h-3.5 flex-shrink-0" />}
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}

export const AuthForms: React.FC = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const passwordValid = PASSWORD_RULES.every((r) => r.test(password));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (mode === 'signup' && !passwordValid) {
      setError('Please meet all password requirements.');
      return;
    }

    setIsLoading(true);
    try {
      if (mode === 'signup') {
        const result = await signUpWithPassword(email, password);
        if (!result.success) { setError(result.error ?? 'Sign up failed'); return; }
        setSuccess('Account created! You can now sign in.');
        setMode('signin');
        setPassword('');
      } else {
        const result = await signInWithPassword(email, password);
        if (!result.success) { setError(result.error ?? 'Sign in failed'); return; }
        navigate('/dashboard');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      {/* Card */}
      <div className="bg-white rounded-2xl shadow-lg p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-2xl font-bold text-purple-600 mb-1">HospRecruit AI</div>
          <h2 className="text-xl font-semibold text-gray-900">
            {mode === 'signin' ? 'Welcome back' : 'Create your account'}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            {mode === 'signin' ? 'Sign in to your account' : 'Start your free trial today'}
          </p>
        </div>

        {/* Toggle */}
        <div className="flex rounded-lg bg-gray-100 p-1 mb-6">
          {(['signin', 'signup'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => { setMode(m); setError(null); setSuccess(null); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition ${
                mode === m ? 'bg-white text-purple-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {m === 'signin' ? 'Sign In' : 'Sign Up'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === 'signup' ? 'Create a strong password' : 'Enter your password'}
                required
                className="w-full pl-10 pr-10 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {mode === 'signup' && <PasswordStrength password={password} />}
          </div>

          {/* Error / Success */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-start gap-2">
              <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" /> {error}
            </div>
          )}
          {success && (
            <div className="p-3 bg-green-50 border border-green-200 text-green-700 rounded-lg text-sm flex items-start gap-2">
              <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" /> {success}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={isLoading || (mode === 'signup' && !passwordValid)}
            className="w-full bg-purple-600 text-white py-2.5 rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center justify-center gap-2 transition"
          >
            {isLoading && <Loader className="w-4 h-4 animate-spin" />}
            {mode === 'signin' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        {/* Footer note */}
        <p className="text-xs text-gray-400 text-center mt-6">
          By continuing you agree to our{' '}
          <a href="/terms" className="text-purple-600 hover:underline">Terms</a> &amp;{' '}
          <a href="/privacy" className="text-purple-600 hover:underline">Privacy Policy</a>
        </p>
      </div>
    </div>
  );
};
