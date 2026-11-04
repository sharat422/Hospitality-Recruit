/**
 * Translation hook for Staff Ops screens.
 *
 * Wraps react-i18next so that a key missing from the active language falls
 * back to English *and* is recorded, rather than silently rendering the raw
 * key (requirement 8). i18next's own `saveMissing` is set at init() time and
 * `src/i18n.ts` must not be touched, so the check is done here explicitly.
 */

import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  type StaffOpsLanguage,
  STAFF_OPS_NAMESPACES,
  hasTranslation,
  recordMissingKey,
  registerStaffOpsLocales,
} from './staffOpsI18n'

type Namespace = (typeof STAFF_OPS_NAMESPACES)[number]

export function useStaffOpsTranslation(namespace: Namespace = 'common') {
  registerStaffOpsLocales()
  const { t, i18n } = useTranslation(namespace)
  const language = (i18n.language?.split('-')[0] || 'en') as StaffOpsLanguage

  const translate = useCallback(
    (key: string, options?: Record<string, unknown>): string => {
      if (language !== 'en' && !hasTranslation(language, namespace, key)) {
        recordMissingKey(language, namespace, key)
        // Explicit English fallback — never show the bare key to a user.
        return t(key, { ...options, lng: 'en' }) as string
      }
      return t(key, options) as string
    },
    [t, language, namespace],
  )

  return { t: translate, language, i18n }
}
