/**
 * API client for HospRecruit AI.
 * Handles auth headers, error handling, base URL.
 */

import { supabase } from '@/lib/supabase'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Inject JWT into every request
apiClient.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  if (data.session?.access_token) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`
  }
  const activePropertyId = localStorage.getItem('hosprecruit.activePropertyId')
  if (activePropertyId) config.headers['X-Property-ID'] = activePropertyId
  return config
})

// Handle 401 and refresh if needed
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const request = error.config as (typeof error.config & { _authRetry?: boolean }) | undefined
    if (error.response?.status === 401 && request && !request._authRetry) {
      request._authRetry = true
      const { data, error: refreshError } = await supabase.auth.refreshSession()
      if (!refreshError && data.session) {
        return apiClient.request(request)
      } else {
        const isEmployeeApp = window.location.pathname.startsWith('/employee-app')
        window.location.href = isEmployeeApp ? '/employee-login' : '/auth'
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
