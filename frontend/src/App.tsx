/**
 * Main app component with routing + providers.
 */

import { Dashboard } from '@/components/Dashboard'
import { ScreeningModule } from '@/components/ScreeningModule'
import { AuthProvider } from '@/hooks/useAuth'
import '@/index.css'
import { LoginPage } from '@/pages/LoginPage'
import { QueryClient,QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter,Navigate,Route,Routes } from 'react-router-dom'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/screening" element={<ScreeningModule jobId="test-job-id" />} />
            <Route path="/" element={<Navigate to="/dashboard" />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
