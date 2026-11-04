/**
 * Mobile-First Application Form (PUBLIC — no auth, no AppLayout)
 * Route: /apply/:jobRoleId
 */

import axios from 'axios'
import { useCallback,useEffect,useRef,useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate,useParams,useSearchParams } from 'react-router-dom'
import { isRTL } from '../i18n'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

const LANGUAGES = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'es', label: 'Español', flag: '🇪🇸' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'de', label: 'Deutsch', flag: '🇩🇪' },
  { code: 'it', label: 'Italiano', flag: '🇮🇹' },
  { code: 'pt', label: 'Português', flag: '🇵🇹' },
]

const AVAILABILITY_OPTIONS = [
  { value: 'immediately', label: 'Immediately' },
  { value: '1_week', label: 'Within 1 week' },
  { value: '2_weeks', label: 'Within 2 weeks' },
  { value: '1_month', label: 'Within 1 month' },
]

const SHIFT_OPTIONS = [
  { value: 'morning', label: 'Morning (6am-2pm)' },
  { value: 'afternoon', label: 'Afternoon (2pm-10pm)' },
  { value: 'evening', label: 'Evening (5pm-1am)' },
  { value: 'nights', label: 'Nights (10pm-6am)' },
  { value: 'weekends', label: 'Weekends' },
]

const CERT_OPTIONS = [
  'Food Safety Level 2',
  'Food Safety Level 3',
  'Personal Licence',
  'WSET Wine',
  'Health & Safety',
  'First Aid',
  'NVQ Hospitality',
]

export default function MobileApplicationForm() {
  const { jobRoleId } = useParams<{ jobRoleId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { t, i18n } = useTranslation('candidate')

  const [lang, setLang] = useState(i18n.language?.split('-')[0] || 'en')
  const [jobRole, setJobRole] = useState<any>(null)
  const [tier, setTier] = useState(1)
  const [applicationId, setApplicationId] = useState<string | null>(null)
  const [formData, setFormData] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [trackingUrl, setTrackingUrl] = useState('')
  const [error, setError] = useState('')
  const [showLangDropdown, setShowLangDropdown] = useState(false)
  const startTime = useRef(Date.now())
  const autoSaveTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const rtl = isRTL(lang)

  const changeLang = (code: string) => {
    setLang(code)
    i18n.changeLanguage(code)
    setShowLangDropdown(false)
    // Reload job role in new language
    fetchJobRole(code)
  }

  const fetchJobRole = useCallback(async (langCode: string) => {
    if (!jobRoleId) return
    try {
      const resp = await axios.get(`${API_BASE}/mobile/jobs/${jobRoleId}/translate`, {
        params: { lang: langCode },
      })
      setJobRole(resp.data)
    } catch {
      setError('Failed to load job details.')
    }
  }, [jobRoleId])

  const startApplication = useCallback(async () => {
    if (!jobRoleId) return
    const referralToken = searchParams.get('token') || searchParams.get('ref')
    try {
      const resp = await axios.post(`${API_BASE}/mobile/applications/start`, {
        job_role_id: jobRoleId,
        source: referralToken ? 'REFERRAL_LINK' : 'DIRECT',
        source_ref: referralToken || undefined,
      })
      setApplicationId(resp.data.application_id)
      setTier(resp.data.tier)
    } catch {
      setError('Failed to start application. Please try again.')
    }
  }, [jobRoleId, searchParams])

  useEffect(() => {
    const init = async () => {
      setLoading(true)
      await Promise.all([fetchJobRole(lang), startApplication()])
      setLoading(false)
    }
    init()
  }, [])

  // Auto-save every 30 seconds
  useEffect(() => {
    if (!applicationId) return
    autoSaveTimer.current = setInterval(async () => {
      try {
        await axios.post(`${API_BASE}/mobile/applications/${applicationId}/save-progress`, {
          form_data: formData,
        })
      } catch {
        // silent fail
      }
    }, 30000)
    return () => {
      if (autoSaveTimer.current) clearInterval(autoSaveTimer.current)
    }
  }, [applicationId, formData])

  const setField = (key: string, value: any) => {
    setFormData((prev) => ({ ...prev, [key]: value }))
  }

  const toggleShift = (shift: string) => {
    const current: string[] = formData.availability_shifts || []
    if (current.includes(shift)) {
      setField('availability_shifts', current.filter((s) => s !== shift))
    } else {
      setField('availability_shifts', [...current, shift])
    }
  }

  const toggleCert = (cert: string) => {
    const current: string[] = formData.certifications || []
    if (current.includes(cert)) {
      setField('certifications', current.filter((c) => c !== cert))
    } else {
      setField('certifications', [...current, cert])
    }
  }

  const getProgress = () => {
    const fields = getRequiredFields()
    if (!fields.length) return 100
    const filled = fields.filter((f) => {
      const v = formData[f]
      if (Array.isArray(v)) return v.length > 0
      return v !== undefined && v !== '' && v !== null
    }).length
    return Math.round((filled / fields.length) * 100)
  }

  const getRequiredFields = () => {
    const base = ['full_name', 'phone', 'right_to_work', 'start_availability']
    if (tier >= 2) return [...base, 'years_experience', 'availability_shifts']
    if (tier >= 3) return [...base, 'years_experience', 'availability_shifts', 'cv_url', 'current_employer', 'linkedin_url']
    return base
  }

  const handleSubmit = async () => {
    if (!applicationId) return
    setSubmitting(true)
    setError('')
    try {
      const elapsedSeconds = Math.round((Date.now() - startTime.current) / 1000)
      const resp = await axios.post(`${API_BASE}/mobile/applications/${applicationId}/submit`, {
        form_data: formData,
        completion_time_seconds: elapsedSeconds,
      })
      setTrackingUrl(resp.data.tracking_url)
      setSubmitted(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || t('common.error'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-600">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 px-4">
        <div className="max-w-lg w-full bg-white rounded-2xl shadow-lg p-8 text-center">
          <div className="text-6xl mb-4">🎉</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">{t('apply.success')}</h1>
          <p className="text-gray-500 mb-6">We'll be in touch soon!</p>
          <button
            onClick={() => navigate(trackingUrl.replace(window.location.origin, ''))}
            className="w-full bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 transition"
          >
            Track Your Application
          </button>
        </div>
      </div>
    )
  }

  const progress = getProgress()

  return (
    <div dir={rtl ? 'rtl' : 'ltr'} className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="sticky top-0 z-20 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Applying for</p>
            <h1 className="text-base font-bold text-gray-900 truncate max-w-xs">
              {jobRole?.title || 'Loading...'}
            </h1>
          </div>
          {/* Language Selector */}
          <div className="relative">
            <button
              onClick={() => setShowLangDropdown((v) => !v)}
              className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 rounded-lg text-sm font-medium hover:bg-gray-200 transition"
            >
              {LANGUAGES.find((l) => l.code === lang)?.flag || '🌐'}
              <span className="hidden sm:inline">{LANGUAGES.find((l) => l.code === lang)?.label}</span>
              <span className="text-gray-400">▼</span>
            </button>
            {showLangDropdown && (
              <div className="absolute right-0 top-10 bg-white border border-gray-200 rounded-xl shadow-lg z-50 min-w-40">
                {LANGUAGES.map((l) => (
                  <button
                    key={l.code}
                    onClick={() => changeLang(l.code)}
                    className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-gray-50 transition first:rounded-t-xl last:rounded-b-xl ${lang === l.code ? 'bg-purple-50 text-purple-700 font-medium' : 'text-gray-700'}`}
                  >
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        {/* Progress bar */}
        <div className="h-1 bg-gray-100">
          <div
            className="h-full bg-purple-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-5">
        {/* LinkedIn fill button */}
        <button
          onClick={() => alert('LinkedIn integration coming soon')}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white py-3 rounded-xl font-medium hover:bg-blue-700 transition shadow-sm"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
          </svg>
          {t('apply.fillLinkedIn')}
        </button>

        {/* Tier 1 Fields */}
        <div className="bg-white rounded-2xl shadow-sm p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Basic Info</h2>

          {/* Full Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">{t('apply.fullName')} *</label>
            <input
              type="text"
              value={formData.full_name || ''}
              onChange={(e) => setField('full_name', e.target.value)}
              placeholder="Your full name"
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400"
            />
          </div>

          {/* Phone */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">{t('apply.phone')} *</label>
            <input
              type="tel"
              value={formData.phone || ''}
              onChange={(e) => setField('phone', e.target.value)}
              placeholder="+44 7700 900000"
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400"
            />
          </div>

          {/* Right to Work */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">{t('apply.rightToWork')} *</label>
            <div className="grid grid-cols-2 gap-3">
              {['YES', 'NO'].map((opt) => (
                <button
                  key={opt}
                  onClick={() => setField('right_to_work', opt)}
                  className={`py-3 rounded-xl font-medium text-sm border-2 transition ${
                    formData.right_to_work === opt
                      ? 'border-purple-500 bg-purple-50 text-purple-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {opt === 'YES' ? '✓ Yes' : '✗ No'}
                </button>
              ))}
            </div>
          </div>

          {/* Start Availability */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">When can you start? *</label>
            <div className="grid grid-cols-2 gap-2">
              {AVAILABILITY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setField('start_availability', opt.value)}
                  className={`py-3 px-2 rounded-xl text-sm font-medium border-2 transition ${
                    formData.start_availability === opt.value
                      ? 'border-purple-500 bg-purple-50 text-purple-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* CV Upload (optional for tier 1, required for tier 3) */}
        <div className="bg-white rounded-2xl shadow-sm p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
              {t('apply.uploadCV')} {tier < 3 ? '(Optional)' : '*'}
            </h2>
            {tier < 3 && (
              <button
                onClick={() => setField('cv_skipped', true)}
                className="text-xs text-purple-600 underline"
              >
                {t('common.skip')}
              </button>
            )}
          </div>
          <div className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center">
            <div className="text-3xl mb-2">📎</div>
            <p className="text-sm text-gray-500 mb-3">Drag & drop your CV or</p>
            <label className="cursor-pointer bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 transition">
              Browse File
              <input
                type="file"
                accept=".pdf,.doc,.docx"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) setField('cv_url', file.name)
                }}
              />
            </label>
            {formData.cv_url && (
              <p className="mt-2 text-xs text-green-600 font-medium">✓ {formData.cv_url}</p>
            )}
          </div>
        </div>

        {/* Tier 2+ Fields */}
        {tier >= 2 && (
          <div className="bg-white rounded-2xl shadow-sm p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Experience & Availability</h2>

            {/* Years Experience */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">{t('apply.experience')} *</label>
              <input
                type="number"
                min="0"
                max="50"
                value={formData.years_experience || ''}
                onChange={(e) => setField('years_experience', parseInt(e.target.value))}
                placeholder="0"
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>

            {/* Shift Availability */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">{t('apply.availability')} *</label>
              <div className="space-y-2">
                {SHIFT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => toggleShift(opt.value)}
                    className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 text-sm transition ${
                      (formData.availability_shifts || []).includes(opt.value)
                        ? 'border-purple-500 bg-purple-50 text-purple-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    <span>{opt.label}</span>
                    {(formData.availability_shifts || []).includes(opt.value) && (
                      <span className="text-purple-500">✓</span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Salary Range */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">{t('apply.salary')} (Optional)</label>
              <select
                value={formData.salary_range || ''}
                onChange={(e) => setField('salary_range', e.target.value)}
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400"
              >
                <option value="">Prefer not to say</option>
                <option value="10-15">£10–15/hr</option>
                <option value="15-20">£15–20/hr</option>
                <option value="20-25">£20–25/hr</option>
                <option value="25-30">£25–30/hr</option>
                <option value="30+">£30+/hr</option>
                <option value="20-25k">£20–25k/yr</option>
                <option value="25-35k">£25–35k/yr</option>
                <option value="35-50k">£35–50k/yr</option>
                <option value="50k+">£50k+/yr</option>
              </select>
            </div>
          </div>
        )}

        {/* Tier 3 Fields */}
        {tier >= 3 && (
          <div className="bg-white rounded-2xl shadow-sm p-5 space-y-4">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Senior Profile</h2>

            {/* Current Employer */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Current Employer *</label>
              <input
                type="text"
                value={formData.current_employer || ''}
                onChange={(e) => setField('current_employer', e.target.value)}
                placeholder="Company name"
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>

            {/* LinkedIn URL */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">LinkedIn URL *</label>
              <input
                type="url"
                value={formData.linkedin_url || ''}
                onChange={(e) => setField('linkedin_url', e.target.value)}
                placeholder="https://linkedin.com/in/yourname"
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>

            {/* Cover Note */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-medium text-gray-700">Cover Note (Optional)</label>
                <span className="text-xs text-gray-400">{(formData.cover_note || '').length}/300</span>
              </div>
              <textarea
                value={formData.cover_note || ''}
                onChange={(e) => setField('cover_note', e.target.value.slice(0, 300))}
                rows={4}
                placeholder="Brief summary of your experience and why you're a great fit..."
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-purple-400 resize-none"
              />
            </div>

            {/* Certifications */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Certifications (Optional)</label>
              <div className="flex flex-wrap gap-2">
                {CERT_OPTIONS.map((cert) => (
                  <button
                    key={cert}
                    onClick={() => toggleCert(cert)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition ${
                      (formData.certifications || []).includes(cert)
                        ? 'bg-purple-600 text-white border-purple-600'
                        : 'border-gray-300 text-gray-600 hover:border-purple-300'
                    }`}
                  >
                    {cert}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={submitting || progress < 40}
          className="w-full bg-purple-600 text-white py-4 rounded-2xl font-bold text-lg hover:bg-purple-700 transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? (
            <span className="flex items-center justify-center gap-2">
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Submitting...
            </span>
          ) : (
            t('apply.submit')
          )}
        </button>

        <p className="text-center text-xs text-gray-400 pb-8">
          Your data is processed securely and never shared without consent.
        </p>
      </div>
    </div>
  )
}
