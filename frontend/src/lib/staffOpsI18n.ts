/**
 * Staff Ops i18n: English, Hindi, Telugu, Tamil, Kannada.
 *
 * This file deliberately does NOT modify `src/i18n.ts`. The only two existing
 * consumers of i18next are candidate-facing recruiting screens
 * (MobileApplicationForm, VideoRecorder) using the `candidate` namespace, and
 * recruiting behaviour must not change. Instead we register additional
 * resource bundles onto the already-initialised instance, which is additive:
 * existing namespaces and languages keep working exactly as before.
 */

import i18n from '../i18n'

import enAgency from '../locales/en/agency.json'
import enAttendance from '../locales/en/attendance.json'
import enCasuals from '../locales/en/casuals.json'
import enCommon from '../locales/en/common.json'
import enLeave from '../locales/en/leave.json'
import enReports from '../locales/en/reports.json'
import enRoster from '../locales/en/roster.json'

import hiAgency from '../locales/hi/agency.json'
import hiAttendance from '../locales/hi/attendance.json'
import hiCasuals from '../locales/hi/casuals.json'
import hiCommon from '../locales/hi/common.json'
import hiLeave from '../locales/hi/leave.json'
import hiReports from '../locales/hi/reports.json'
import hiRoster from '../locales/hi/roster.json'

import knAgency from '../locales/kn/agency.json'
import knAttendance from '../locales/kn/attendance.json'
import knCasuals from '../locales/kn/casuals.json'
import knCommon from '../locales/kn/common.json'
import knLeave from '../locales/kn/leave.json'
import knReports from '../locales/kn/reports.json'
import knRoster from '../locales/kn/roster.json'

import taAgency from '../locales/ta/agency.json'
import taAttendance from '../locales/ta/attendance.json'
import taCasuals from '../locales/ta/casuals.json'
import taCommon from '../locales/ta/common.json'
import taLeave from '../locales/ta/leave.json'
import taReports from '../locales/ta/reports.json'
import taRoster from '../locales/ta/roster.json'

import teAgency from '../locales/te/agency.json'
import teAttendance from '../locales/te/attendance.json'
import teCasuals from '../locales/te/casuals.json'
import teCommon from '../locales/te/common.json'
import teLeave from '../locales/te/leave.json'
import teReports from '../locales/te/reports.json'
import teRoster from '../locales/te/roster.json'

export const STAFF_OPS_LANGUAGES = [
  { code: 'en', label: 'English', nativeLabel: 'English' },
  { code: 'hi', label: 'Hindi', nativeLabel: 'हिंदी' },
  { code: 'te', label: 'Telugu', nativeLabel: 'తెలుగు' },
  { code: 'ta', label: 'Tamil', nativeLabel: 'தமிழ்' },
  { code: 'kn', label: 'Kannada', nativeLabel: 'ಕನ್ನಡ' },
] as const

export type StaffOpsLanguage = (typeof STAFF_OPS_LANGUAGES)[number]['code']

export const STAFF_OPS_NAMESPACES = [
  'common', 'roster', 'attendance', 'leave', 'casuals', 'agency', 'reports',
] as const

const BUNDLES: Record<string, Record<string, object>> = {
  en: { common: enCommon, roster: enRoster, attendance: enAttendance, leave: enLeave,
        casuals: enCasuals, agency: enAgency, reports: enReports },
  hi: { common: hiCommon, roster: hiRoster, attendance: hiAttendance, leave: hiLeave,
        casuals: hiCasuals, agency: hiAgency, reports: hiReports },
  te: { common: teCommon, roster: teRoster, attendance: teAttendance, leave: teLeave,
        casuals: teCasuals, agency: teAgency, reports: teReports },
  ta: { common: taCommon, roster: taRoster, attendance: taAttendance, leave: taLeave,
        casuals: taCasuals, agency: taAgency, reports: taReports },
  kn: { common: knCommon, roster: knRoster, attendance: knAttendance, leave: knLeave,
        casuals: knCasuals, agency: knAgency, reports: knReports },
}

let registered = false

/** Register Staff Ops bundles. Safe to call more than once. */
export function registerStaffOpsLocales(): void {
  if (registered) return
  for (const [lang, namespaces] of Object.entries(BUNDLES)) {
    for (const [ns, resources] of Object.entries(namespaces)) {
      // deep=false, overwrite=false: never clobber an existing bundle, so the
      // recruiting `candidate` namespace cannot be affected.
      i18n.addResourceBundle(lang, ns, resources, false, false)
    }
  }
  registered = true
}

registerStaffOpsLocales()

// ---------------------------------------------------------------------------
// Missing-key tracking (requirement 8)
// ---------------------------------------------------------------------------

export type MissingKey = { language: string; namespace: string; key: string }

const missing = new Map<string, MissingKey>()

/** Record a key with no translation in the active language. */
export function recordMissingKey(language: string, namespace: string, key: string): void {
  const id = `${language}:${namespace}:${key}`
  if (missing.has(id)) return
  missing.set(id, { language, namespace, key })
  if (import.meta.env.DEV) {
    console.warn(`[i18n] missing "${key}" in ${language}/${namespace} — falling back to English`)
  }
}

export function getMissingKeys(): MissingKey[] {
  return [...missing.values()]
}

export function clearMissingKeys(): void {
  missing.clear()
}

/**
 * Does this language actually carry this key?
 * Used to decide whether a render fell back to English.
 */
export function hasTranslation(language: string, namespace: string, key: string): boolean {
  const bundle = BUNDLES[language]?.[namespace] as Record<string, string> | undefined
  return Boolean(bundle && key in bundle)
}

// ---------------------------------------------------------------------------
// Default language from the hotel's state (requirement 3)
// ---------------------------------------------------------------------------

/**
 * `properties.state` is free text (VARCHAR(100)), so match on both the state
 * name and the common two-letter code. Anything unmatched falls back to
 * English rather than guessing.
 */
const STATE_TO_LANGUAGE: Record<string, StaffOpsLanguage> = {
  telangana: 'te', ts: 'te', tg: 'te',
  'andhra pradesh': 'te', ap: 'te',
  'tamil nadu': 'ta', tamilnadu: 'ta', tn: 'ta', puducherry: 'ta', py: 'ta',
  karnataka: 'kn', ka: 'kn',
  // Hindi-speaking states
  'uttar pradesh': 'hi', up: 'hi',
  'madhya pradesh': 'hi', mp: 'hi',
  bihar: 'hi', br: 'hi',
  rajasthan: 'hi', rj: 'hi',
  haryana: 'hi', hr: 'hi',
  delhi: 'hi', dl: 'hi', 'new delhi': 'hi',
  jharkhand: 'hi', jh: 'hi',
  chhattisgarh: 'hi', cg: 'hi',
  uttarakhand: 'hi', uk: 'hi', ut: 'hi',
  'himachal pradesh': 'hi', hp: 'hi',
}

export function defaultLanguageForState(state?: string | null): StaffOpsLanguage {
  if (!state) return 'en'
  return STATE_TO_LANGUAGE[state.trim().toLowerCase()] ?? 'en'
}

/**
 * Resolve which language to show, in priority order:
 *   1. what the user chose and we saved
 *   2. the hotel's state default
 *   3. English
 * The browser language detector is deliberately not consulted: a hotel laptop
 * set to en-US should still show Tamil to a Tamil-speaking supervisor.
 */
export function resolveLanguage(
  userPreference?: string | null,
  hotelState?: string | null,
): StaffOpsLanguage {
  const supported = STAFF_OPS_LANGUAGES.map(l => l.code) as readonly string[]
  if (userPreference && supported.includes(userPreference)) {
    return userPreference as StaffOpsLanguage
  }
  return defaultLanguageForState(hotelState)
}

export async function changeLanguage(language: StaffOpsLanguage): Promise<void> {
  await i18n.changeLanguage(language)
  document.documentElement.lang = language
}

export default i18n
