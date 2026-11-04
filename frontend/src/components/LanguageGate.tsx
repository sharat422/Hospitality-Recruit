import { useEffect, useState } from 'react'
import apiClient from '../lib/api'
import { changeLanguage, type StaffOpsLanguage } from '../lib/staffOpsI18n'
import LanguagePicker from './LanguagePicker'

/**
 * Shows the language picker once, on first login, then never again.
 *
 * Mounted inside ProtectedRoute so it covers every signed-in screen including
 * the employee PWA at /employee-app, which does not use AppLayout. Public
 * candidate routes (/apply/:jobRoleId, /track/:token) are not wrapped by
 * ProtectedRoute, so recruiting is unaffected.
 *
 * Fails open by design: if the language endpoint is unreachable we render the
 * app in whatever language is already active rather than trapping someone
 * behind a picker they cannot get past.
 */

type Phase = 'checking' | 'choose' | 'ready'

export default function LanguageGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>('checking')

  useEffect(() => {
    let cancelled = false

    const decide = async () => {
      try {
        const { data } = await apiClient.get('/staff-ops/me/language')
        if (cancelled) return

        // Apply whatever the server resolved (saved choice, else hotel state).
        if (data?.resolved_language) {
          await changeLanguage(data.resolved_language as StaffOpsLanguage)
        }
        // Ask only when the person has never chosen for themselves.
        setPhase(data?.preferred_language ? 'ready' : 'choose')
      } catch {
        // Endpoint down, migration not yet applied, or offline — let them in.
        if (!cancelled) setPhase('ready')
      }
    }

    void decide()
    return () => { cancelled = true }
  }, [])

  if (phase === 'checking') return null       // ProtectedRoute already showed a spinner
  if (phase === 'choose') {
    return <LanguagePicker variant="first-login" onChosen={() => setPhase('ready')} />
  }
  return <>{children}</>
}
