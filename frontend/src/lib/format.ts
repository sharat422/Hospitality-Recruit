/**
 * Shared formatting for Staff Ops (requirement 6, and PLAN.md section 8).
 *
 *   - digits are always 0-9, never native-script numerals
 *   - money and counts use Indian grouping: 1,00,000 not 100,000
 *   - dates are DD-MM-YYYY
 *   - times are 12-hour with AM/PM, in the local word where one reads naturally
 *   - everything is pinned to Asia/Kolkata
 *
 * The `-u-nu-latn` suffix on every locale is load-bearing: without it,
 * `Intl.NumberFormat('hi-IN')` can emit Devanagari digits (१,२,३) on some
 * platforms, which hotel staff do not expect on a payslip or a roster.
 */

export const IST = 'Asia/Kolkata'

/**
 * Number formatting is pinned to en-IN for EVERY language, not to the active
 * one.
 *
 * ICU's `kn-IN` locale groups digits the Western way, so
 * `Intl.NumberFormat('kn-IN').format(10000000)` returns "10,000,000" — a
 * crore rendered as ten million, on a Kannada payslip. hi, te and ta happen
 * to group correctly today, but relying on each locale to agree is the bug.
 *
 * Grouping and digits must be identical in all five languages, so one locale
 * decides both. `-u-nu-latn` additionally forces 0-9 rather than Devanagari
 * or other native numerals.
 */
const NUMERIC_LOCALE = 'en-IN-u-nu-latn'

function numericLocale(_language = 'en'): string {
  return NUMERIC_LOCALE
}

function toDate(value: Date | string | number | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** DD-MM-YYYY, e.g. 29-10-2026. */
export function formatDate(
  value: Date | string | number | null | undefined,
  language = 'en',
): string {
  const date = toDate(value)
  if (!date) return '—'
  const parts = new Intl.DateTimeFormat(numericLocale(language), {
    timeZone: IST, day: '2-digit', month: '2-digit', year: 'numeric',
  }).formatToParts(date)
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  return `${get('day')}-${get('month')}-${get('year')}`
}

/** e.g. 29 Oct 2026 — for headings where DD-MM-YYYY reads poorly. */
export function formatDateLong(
  value: Date | string | number | null | undefined,
  language = 'en',
): string {
  const date = toDate(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat(numericLocale(language), {
    timeZone: IST, day: '2-digit', month: 'short', year: 'numeric',
  }).format(date)
}

/**
 * 12-hour time, e.g. 09:30 AM.
 *
 * AM/PM stays in Latin in every language. The formal local equivalents
 * (पूर्वाह्न, முற்பகல், ಪೂರ್ವಾಹ್ನ) are correct but bookish; Indian apps
 * universally show AM/PM and staff read it without thinking. The `language`
 * parameter is kept so callers need not special-case time formatting.
 */
export function formatTime(
  value: Date | string | number | null | undefined,
  _language = 'en',
): string {
  const date = toDate(value)
  if (!date) return '—'
  const parts = new Intl.DateTimeFormat('en-IN-u-nu-latn', {
    timeZone: IST, hour: '2-digit', minute: '2-digit', hour12: true,
  }).formatToParts(date)
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  const isPM = get('dayPeriod').toUpperCase().includes('PM')
  return `${get('hour')}:${get('minute')} ${isPM ? 'PM' : 'AM'}`
}

/** DD-MM-YYYY plus 12-hour time. */
export function formatDateTime(
  value: Date | string | number | null | undefined,
  language = 'en',
): string {
  const date = toDate(value)
  if (!date) return '—'
  return `${formatDate(date, language)} ${formatTime(date, language)}`
}

/** Indian grouping, e.g. 1,00,000. */
export function formatNumber(value: number | string | null | undefined, language = 'en'): string {
  const n = typeof value === 'string' ? Number(value) : value
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return new Intl.NumberFormat(numericLocale(language)).format(n)
}

/** Rupees with Indian grouping, e.g. ₹1,00,000 or ₹12,500.50. */
export function formatINR(
  value: number | string | null | undefined,
  language = 'en',
  options: { paise?: boolean } = {},
): string {
  const n = typeof value === 'string' ? Number(value) : value
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const showPaise = options.paise ?? !Number.isInteger(n)
  return new Intl.NumberFormat(numericLocale(language), {
    style: 'currency', currency: 'INR',
    minimumFractionDigits: showPaise ? 2 : 0,
    maximumFractionDigits: showPaise ? 2 : 0,
  }).format(n)
}

/** Worked time as hours and minutes, e.g. "8h 30m". */
export function formatDuration(minutes: number | null | undefined, language = 'en'): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return '—'
  const whole = Math.max(0, Math.round(minutes))
  const h = Math.floor(whole / 60)
  const m = whole % 60
  return `${formatNumber(h, language)}h ${formatNumber(m, language)}m`
}

/** Today's date in IST as YYYY-MM-DD, for API parameters. */
export function todayIST(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: IST, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}
