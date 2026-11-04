/**
 * Mobile Feature Hub — Overview page for all mobile features
 * Route: /mobile-features
 */

import { apiClient } from '@/lib/api'
import { useEffect,useState } from 'react'
import { Link } from 'react-router-dom'
import { AppLayout } from '../components/AppLayout'

interface Stats {
  total_applications: number
  qr_scan_to_apply_rate: number
  most_used_language: string
}

const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', flag: '🇬🇧', native: 'English' },
  { code: 'es', name: 'Spanish', flag: '🇪🇸', native: 'Español' },
  { code: 'fr', name: 'French', flag: '🇫🇷', native: 'Français' },
  { code: 'de', name: 'German', flag: '🇩🇪', native: 'Deutsch' },
  { code: 'it', name: 'Italian', flag: '🇮🇹', native: 'Italiano' },
  { code: 'pt', name: 'Portuguese', flag: '🇵🇹', native: 'Português' },
  { code: 'zh', name: 'Chinese', flag: '🇨🇳', native: '中文' },
  { code: 'ar', name: 'Arabic', flag: '🇸🇦', native: 'العربية' },
  { code: 'ja', name: 'Japanese', flag: '🇯🇵', native: '日本語' },
  { code: 'ko', name: 'Korean', flag: '🇰🇷', native: '한국어' },
  { code: 'pl', name: 'Polish', flag: '🇵🇱', native: 'Polski' },
  { code: 'ro', name: 'Romanian', flag: '🇷🇴', native: 'Română' },
]

export default function MobileFeatureHub() {
  const [stats, setStats] = useState<Stats>({
    total_applications: 0,
    qr_scan_to_apply_rate: 0,
    most_used_language: 'en',
  })
  const [loading, setLoading] = useState(true)
  const [translateJobRoleId, setTranslateJobRoleId] = useState('')
  const [translateLang, setTranslateLang] = useState('es')
  const [translating, setTranslating] = useState(false)
  const [translationResult, setTranslationResult] = useState<any>(null)
  const [jobRoles, setJobRoles] = useState<any[]>([])

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch applications stats
        const [appsResp, qrResp] = await Promise.allSettled([
          apiClient.get('/mobile/applications'),
          apiClient.get('/mobile/qr-codes'),
        ])

        let totalApps = 0
        let qrRate = 0
        let topLang = 'en'

        if (appsResp.status === 'fulfilled') {
          const apps = appsResp.value.data.applications || []
          totalApps = apps.length

          // Find most used language from lang prefs (approximate from form data)
          const langCount: Record<string, number> = {}
          apps.forEach((a: any) => {
            const l = a.form_data?.language || 'en'
            langCount[l] = (langCount[l] || 0) + 1
          })
          if (Object.keys(langCount).length > 0) {
            topLang = Object.entries(langCount).sort((a, b) => b[1] - a[1])[0][0]
          }
        }

        if (qrResp.status === 'fulfilled') {
          const qrs = qrResp.value.data.qr_codes || []
          const totalScans = qrs.reduce((s: number, q: any) => s + q.scan_count, 0)
          const totalAppsByQR = qrs.reduce((s: number, q: any) => s + q.application_count, 0)
          qrRate = totalScans > 0 ? Math.round((totalAppsByQR / totalScans) * 100) : 0
        }

        setStats({ total_applications: totalApps, qr_scan_to_apply_rate: qrRate, most_used_language: topLang })
      } catch {
        // non-fatal
      } finally {
        setLoading(false)
      }
    }

    const fetchJobRoles = async () => {
      try {
        const resp = await apiClient.get('/ai-screening/job-roles')
        setJobRoles(resp.data.job_roles || resp.data || [])
      } catch {
        // non-fatal
      }
    }

    fetchData()
    fetchJobRoles()
  }, [])

  const handleTranslate = async () => {
    if (!translateJobRoleId || !translateLang) return
    setTranslating(true)
    setTranslationResult(null)
    try {
      const resp = await apiClient.post(`/mobile/translations/job-role/${translateJobRoleId}`, {
        target_language: translateLang,
      })
      setTranslationResult(resp.data)
    } catch {
      setTranslationResult({ error: 'Translation failed.' })
    } finally {
      setTranslating(false)
    }
  }

  const featureCards = [
    {
      title: 'Application Form',
      description: 'Tiered mobile-first application form with auto-save and LinkedIn prefill. Works great on any device.',
      icon: '📋',
      color: 'bg-purple-50 border-purple-200',
      iconBg: 'bg-purple-100',
      action: { label: 'Test Form (needs job ID)', to: '/apply/demo' },
      stats: [`${stats.total_applications} applications submitted`],
    },
    {
      title: 'Video Interviews',
      description: 'Candidates record video or audio responses on their phone. Recruiters review with speed controls and star ratings.',
      icon: '🎬',
      color: 'bg-blue-50 border-blue-200',
      iconBg: 'bg-blue-100',
      action: { label: 'Review Interviews', to: '/video-review/new' },
      stats: ['Mobile-optimized recorder', 'Audio-only fallback'],
    },
    {
      title: 'QR Codes',
      description: 'Generate QR codes for job postings, referral campaigns, or events. Track scans and applications in real time.',
      icon: '📱',
      color: 'bg-green-50 border-green-200',
      iconBg: 'bg-green-100',
      action: { label: 'Manage QR Codes', to: '/qr-codes' },
      stats: [`${stats.qr_scan_to_apply_rate}% scan-to-apply rate`],
    },
    {
      title: 'Multi-Language',
      description: `Support candidates in ${SUPPORTED_LANGUAGES.length} languages. AI-powered translation powered by Claude with DeepL fallback.`,
      icon: '🌐',
      color: 'bg-orange-50 border-orange-200',
      iconBg: 'bg-orange-100',
      action: null,
      stats: [`Most used: ${SUPPORTED_LANGUAGES.find(l => l.code === stats.most_used_language)?.name || 'English'}`],
    },
  ]

  return (
    <AppLayout>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Mobile Features Hub</h1>
          <p className="text-gray-500">Feature 04 — Mobile-First Candidate Experience</p>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm text-center">
            <p className="text-3xl font-bold text-purple-700 mb-1">
              {loading ? '...' : stats.total_applications}
            </p>
            <p className="text-sm text-gray-500">Mobile Applications</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm text-center">
            <p className="text-3xl font-bold text-green-700 mb-1">
              {loading ? '...' : `${stats.qr_scan_to_apply_rate}%`}
            </p>
            <p className="text-sm text-gray-500">QR Conversion Rate</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm text-center">
            <p className="text-3xl font-bold text-orange-600 mb-1">{SUPPORTED_LANGUAGES.length}</p>
            <p className="text-sm text-gray-500">Languages Supported</p>
          </div>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-8">
          {featureCards.map((card) => (
            <div key={card.title} className={`rounded-2xl border p-6 ${card.color}`}>
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 ${card.iconBg}`}>
                  {card.icon}
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-bold text-gray-900 mb-1.5">{card.title}</h3>
                  <p className="text-sm text-gray-600 mb-3">{card.description}</p>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {card.stats.map((s) => (
                      <span key={s} className="text-xs bg-white px-2 py-1 rounded-full text-gray-600 border border-gray-200">
                        {s}
                      </span>
                    ))}
                  </div>
                  {card.action && (
                    <Link
                      to={card.action.to}
                      className="inline-flex items-center gap-1 text-sm font-medium text-purple-700 hover:text-purple-900 transition"
                    >
                      {card.action.label} →
                    </Link>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Translation section */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 mb-6">
          <h2 className="text-lg font-bold text-gray-900 mb-1">Job Role Translation</h2>
          <p className="text-sm text-gray-500 mb-5">Translate a job role into any supported language using AI.</p>

          <div className="flex flex-col sm:flex-row gap-3 mb-4">
            <select
              value={translateJobRoleId}
              onChange={(e) => setTranslateJobRoleId(e.target.value)}
              className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm"
            >
              <option value="">Select job role...</option>
              {jobRoles.map((jr) => (
                <option key={jr.id} value={jr.id}>{jr.title}</option>
              ))}
            </select>
            <select
              value={translateLang}
              onChange={(e) => setTranslateLang(e.target.value)}
              className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm"
            >
              {SUPPORTED_LANGUAGES.filter(l => l.code !== 'en').map((l) => (
                <option key={l.code} value={l.code}>{l.flag} {l.name}</option>
              ))}
            </select>
            <button
              onClick={handleTranslate}
              disabled={translating || !translateJobRoleId}
              className="bg-purple-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-purple-700 transition disabled:opacity-50 whitespace-nowrap"
            >
              {translating ? 'Translating...' : 'Translate'}
            </button>
          </div>

          {translationResult && !translationResult.error && (
            <div className="bg-gray-50 rounded-xl p-4 text-sm">
              <p className="font-semibold text-gray-900 mb-1">{translationResult.translated_title}</p>
              <p className="text-gray-600 text-xs leading-relaxed">{translationResult.translated_description}</p>
              <p className="text-xs text-green-600 mt-2">Translated by: {translationResult.translated_by}</p>
            </div>
          )}

          {translationResult?.error && (
            <p className="text-sm text-red-500">{translationResult.error}</p>
          )}
        </div>

        {/* Supported Languages list */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">Supported Languages</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {SUPPORTED_LANGUAGES.map((lang) => (
              <div key={lang.code} className="flex items-center gap-2.5 p-3 bg-gray-50 rounded-xl border border-gray-100">
                <span className="text-xl">{lang.flag}</span>
                <div>
                  <p className="text-sm font-medium text-gray-900">{lang.name}</p>
                  <p className="text-xs text-gray-400">{lang.native}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
