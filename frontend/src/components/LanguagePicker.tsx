import { Check, Globe, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import apiClient from '../lib/api'
import { useProperty } from '../lib/PropertyContext'
import {
  STAFF_OPS_LANGUAGES,
  type StaffOpsLanguage,
  changeLanguage,
  resolveLanguage,
} from '../lib/staffOpsI18n'
import { useStaffOpsTranslation } from '../lib/useStaffOpsTranslation'

const STORAGE_KEY = 'hosprecruit.language'

/**
 * Language picker (requirement 3).
 *
 * `variant="first-login"` is the full-screen card a staff member sees once,
 * before anything else. `variant="profile"` is the compact control for the
 * profile screen and the top bar.
 *
 * The choice is saved on the user so it follows them to any device. The
 * localStorage copy is only a cache so the next cold start does not flash
 * English before the profile loads.
 */
export default function LanguagePicker({
  variant = 'profile',
  onChosen,
}: {
  variant?: 'profile' | 'first-login'
  onChosen?: (language: StaffOpsLanguage) => void
}) {
  const { t, language } = useStaffOpsTranslation('common')
  const { activeProperty } = useProperty()
  const [saving, setSaving] = useState<StaffOpsLanguage | null>(null)
  const [error, setError] = useState('')

  // Seed from the hotel's state the first time, so a Chennai hotel opens in
  // Tamil rather than English before the user has chosen anything.
  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return
    const seeded = resolveLanguage(null, (activeProperty as { state?: string } | null)?.state)
    if (seeded !== language) void changeLanguage(seeded)
  }, [activeProperty, language])

  const choose = async (code: StaffOpsLanguage) => {
    setSaving(code)
    setError('')
    try {
      await changeLanguage(code)
      try {
        localStorage.setItem(STORAGE_KEY, code)
      } catch {
        // Private browsing or blocked storage: the server copy still holds.
      }
      // Persist against the user so the choice follows them across devices.
      await apiClient.put('/staff-ops/me/language', { preferred_language: code })
      onChosen?.(code)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      // The language already changed on screen; only the save failed.
      setError(detail || t('error'))
    } finally {
      setSaving(null)
    }
  }

  const options = (
    <div className={variant === 'first-login' ? 'grid gap-2' : 'grid gap-1'}>
      {STAFF_OPS_LANGUAGES.map(option => {
        const active = option.code === language
        return (
          <button
            key={option.code}
            onClick={() => void choose(option.code)}
            disabled={saving !== null}
            aria-current={active}
            lang={option.code}
            className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition
              ${active ? 'border-purple-500 bg-purple-50' : 'border-slate-200 hover:bg-slate-50'}
              disabled:opacity-60`}
          >
            <span className="min-w-0">
              <span className="block text-base font-medium text-slate-900">{option.nativeLabel}</span>
              {option.nativeLabel !== option.label && (
                <span className="block text-xs text-slate-500">{option.label}</span>
              )}
            </span>
            {saving === option.code
              ? <Loader2 className="h-5 w-5 shrink-0 animate-spin text-purple-600" />
              : active && <Check className="h-5 w-5 shrink-0 text-purple-600" />}
          </button>
        )
      })}
    </div>
  )

  if (variant === 'first-login') {
    return (
      <div className="staff-ops flex min-h-screen items-center justify-center bg-slate-50 p-4">
        <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6">
          <div className="mb-5 flex items-center gap-2">
            <Globe className="h-5 w-5 text-purple-600" />
            <h1 className="text-lg font-semibold text-slate-900">{t('selectLanguage')}</h1>
          </div>
          {options}
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        </div>
      </div>
    )
  }

  return (
    <section className="staff-ops">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
        <Globe className="h-4 w-4 text-slate-400" /> {t('language')}
      </h2>
      {options}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  )
}
