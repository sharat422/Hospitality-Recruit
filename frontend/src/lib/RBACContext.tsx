import React,{ createContext,useCallback,useContext,useEffect,useMemo,useState } from 'react'
import apiClient from './api'
import { useAuth } from './AuthContext'

export type Role = 'OWNER' | 'GROUP_ADMIN_HR' | 'GENERAL_MANAGER' | 'HR_MANAGER' |
  'DEPARTMENT_HEAD' | 'RECRUITER' | 'EMPLOYEE' | 'CANDIDATE'

export interface AccessProfile {
  userId: string
  orgId: string
  role: Role
  permissions: string[]
  activePropertyId: string | null
  propertyIds: string[]
  departmentId: string | null
  departmentIds: string[]
}

interface RBACValue {
  profile: AccessProfile | null
  loading: boolean
  error: string | null
  can: (permission: string) => boolean
  refresh: () => Promise<void>
}

const RBACContext = createContext<RBACValue | undefined>(undefined)

export function RBACProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const [profile, setProfile] = useState<AccessProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setProfile(null)
      return
    }
    setLoading(true)
    try {
      const { data } = await apiClient.get<AccessProfile>('/rbac/me')
      setProfile(data)
      setError(null)
    } catch {
      setProfile(null)
      setError('Your role and property access could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!authLoading) void refresh()
  }, [authLoading, refresh])

  const value = useMemo<RBACValue>(() => ({
    profile,
    loading: loading || authLoading,
    error,
    can: permission => Boolean(profile?.permissions.includes(permission)),
    refresh,
  }), [profile, loading, authLoading, error, refresh])

  return <RBACContext.Provider value={value}>{children}</RBACContext.Provider>
}

export function useRBAC() {
  const value = useContext(RBACContext)
  if (!value) throw new Error('useRBAC must be used within RBACProvider')
  return value
}
