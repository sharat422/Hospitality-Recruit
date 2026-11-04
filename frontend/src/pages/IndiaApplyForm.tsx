/**
 * IndiaApplyForm — 60-second mobile application form for Indian hotel hiring.
 * Req 4: OTP login via phone number.
 * Req 5: Max 5 fields for entry-level roles.
 * Req 6: Tracks QR code source.
 * Public route — no authentication required.
 * Mobile-first, bilingual Hindi + English.
 */

import { apiClient } from '@/lib/api'
import {
AlertCircle,
Building2,
Check,
CheckCircle2,
ChevronRight,
IndianRupee,
Loader,
MessageCircle,
Phone,
Upload,
WifiOff,
Zap
} from 'lucide-react'
import { useEffect,useRef,useState } from 'react'
import { useParams,useSearchParams } from 'react-router-dom'

const SOURCES = [
  { value: 'naukri',       label: 'Naukri.com'  },
  { value: 'apna',         label: 'Apna App'    },
  { value: 'workindia',    label: 'WorkIndia'   },
  { value: 'shine',        label: 'Shine.com'   },
  { value: 'indeed_india', label: 'Indeed'      },
  { value: 'whatsapp',     label: 'WhatsApp'    },
  { value: 'referral',     label: 'किसी ने बताया (Referral)' },
  { value: 'walk_in',      label: 'Walk-in'     },
  { value: 'qr_code',      label: 'QR Code'     },
  { value: 'other',        label: 'Other / अन्य' },
]

const EXP_OPTIONS = [
  { value: 0, label: 'Fresher — पहली नौकरी' },
  { value: 1, label: '1 साल से कम' },
  { value: 2, label: '1–2 साल' },
  { value: 3, label: '2–5 साल' },
  { value: 5, label: '5+ साल' },
]

type Step = 'phone' | 'otp' | 'form' | 'done'

interface JobInfo {
  id: string; title: string; property_name?: string; department?: string
  location_city?: string; jd_english?: string; jd_hindi?: string
  salary_min_inr?: number; salary_max_inr?: number
  experience_min_years?: number; is_urgent?: boolean
  whatsapp_apply_url?: string
}

export default function IndiaApplyForm() {
  const { jobId }          = useParams<{ jobId: string }>()
  const [searchParams]     = useSearchParams()
  const orgId              = searchParams.get('org') || ''
  const srcParam           = searchParams.get('src') || 'other'
  const distributionToken = searchParams.get('dist') || ''
  const isQR               = srcParam === 'qr_code'

  const [step,         setStep]         = useState<Step>('phone')
  const startedAt = useRef(Date.now())
  const [language, setLanguage] = useState<'hi' | 'en'>('hi')
  const [online, setOnline] = useState(navigator.onLine)
  const connection = (navigator as any).connection
  const lowBandwidth = Boolean(connection?.saveData || ['slow-2g', '2g'].includes(connection?.effectiveType))
  const [job,          setJob]          = useState<JobInfo | null>(null)
  const [jobLoading,   setJobLoading]   = useState(true)
  const [jobError,     setJobError]     = useState('')

  // Phone + OTP
  const [phone,        setPhone]        = useState('')
  const [otp,          setOtp]          = useState('')
  const [otpSending,   setOtpSending]   = useState(false)
  const [otpError,     setOtpError]     = useState('')
  const [verificationToken, setVerificationToken] = useState('')
  const [countdown,    setCountdown]    = useState(0)

  // 5-field form
  const [name,         setName]         = useState('')
  const [expYears,     setExpYears]     = useState(0)
  const [city,         setCity]         = useState('')
  const [source,       setSource]       = useState(srcParam)
  const [sourceDetail, setSourceDetail] = useState('')
  const [submitting,   setSubmitting]   = useState(false)
  const [submitError,  setSubmitError]  = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [trackingToken, setTrackingToken] = useState('')
  const [trackingUrl, setTrackingUrl] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState('')

  // Load job info
  useEffect(() => {
    if (!jobId) return
    apiClient.get(`/recruit/apply/job/${jobId}`)
      .then(r => setJob(r.data))
      .catch(() => setJobError('Job not found or no longer active.'))
      .finally(() => setJobLoading(false))

    // Log QR scan
    if (isQR && orgId) {
      apiClient.post('/recruit/apply/qr-scan', { job_id: jobId, org_id: orgId, source: srcParam })
        .catch(() => null)
    }
  }, [jobId, orgId, isQR, srcParam])

  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update) }
  }, [])

  // OTP countdown
  useEffect(() => {
    if (countdown <= 0) return
    const t = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [countdown])

  const sendOtp = async () => {
    if (!phone || phone.length < 10) { setOtpError('Valid mobile number required / सही नंबर डालें'); return }
    setOtpSending(true); setOtpError('')
    try {
      const fullPhone = phone.startsWith('+') ? phone : `+91${phone.replace(/^0+/, '')}`
      await apiClient.post('/recruit/apply/otp/send', { phone: fullPhone, job_id: jobId, org_id: orgId })
      setPhone(fullPhone)
      setStep('otp')
      setCountdown(60)
    } catch (e: any) {
      setOtpError(e.response?.data?.detail ?? 'OTP send failed. Please try again.')
    } finally {
      setOtpSending(false)
    }
  }

  const verifyOtp = async () => {
    if (otp.length !== 6) { setOtpError('6-digit OTP required'); return }
    setSubmitting(true); setOtpError('')
    try {
      const res = await apiClient.post('/recruit/apply/otp/check', {
        phone, otp, job_id: jobId, org_id: orgId,
      })
      setVerificationToken(res.data.verification_token)
      setStep('form')
    } catch (e: any) {
      setOtpError(e.response?.data?.detail ?? 'Incorrect OTP')
    } finally {
      setSubmitting(false)
    }
  }

  const submitApplication = async () => {
    if (!name.trim()) { setSubmitError('Name is required / नाम जरूरी है'); return }
    setSubmitting(true); setSubmitError('')
    try {
      const res = await apiClient.post('/recruit/apply/otp/verify', {
        phone,
        verification_token: verificationToken,
        job_id:           jobId,
        org_id:           orgId,
        name:             name.trim(),
        experience_years: expYears,
        current_city:     city,
        source,
        source_detail:    sourceDetail || undefined,
        via_qr:           isQR,
        distribution_token: distributionToken || undefined,
        completion_time_seconds: Math.round((Date.now() - startedAt.current) / 1000),
        preferred_language: language,
        low_bandwidth_mode: lowBandwidth,
      })
      if (res.data?.verified) {
        setApplicationId(res.data.application_id || '')
        setTrackingToken(res.data.tracking_token || '')
        setTrackingUrl(res.data.tracking_url || '')
        setStep('done')
      } else {
        setSubmitError(res.data?.error ?? 'OTP verification failed')
      }
    } catch (e: any) {
      setSubmitError(e.response?.data?.detail ?? 'Application failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const uploadDocument = async (file: File, documentType: string) => {
    if (!trackingToken || !applicationId) return
    setUploading(true); setUploadMessage('')
    const data = new FormData()
    data.append('application_id', applicationId)
    data.append('document_type', documentType)
    data.append('file', file)
    try {
      await apiClient.post(`/recruit/apply/documents/${trackingToken}`, data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadMessage(language === 'hi' ? 'दस्तावेज़ अपलोड हो गया।' : 'Document uploaded.')
    } catch (e: any) {
      setUploadMessage(e.response?.data?.detail ?? 'Upload failed. You can retry later.')
    } finally { setUploading(false) }
  }

  // ── Loading ──────────────────────────────────────────────────────────────
  if (jobLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 to-white flex items-center justify-center">
        <Loader className="w-8 h-8 text-purple-600 animate-spin" />
      </div>
    )
  }

  if (jobError || !job) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-sm w-full text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-lg font-bold text-gray-800 mb-2">Job Not Available</h2>
          <p className="text-gray-500 text-sm">{jobError || 'This job is no longer active.'}</p>
        </div>
      </div>
    )
  }

  // ── Common header ─────────────────────────────────────────────────────────
  const Header = () => (
    <div className="bg-white border-b border-gray-100 px-5 py-4">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center flex-shrink-0">
          <Building2 className="w-5 h-5 text-purple-600" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="font-bold text-gray-900 text-base leading-tight">{job.title}</h1>
            {job.is_urgent && (
              <span className="text-[10px] font-bold bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full flex items-center gap-0.5">
                <Zap className="w-2.5 h-2.5" />Urgent
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            {[job.property_name, job.department, job.location_city].filter(Boolean).join(' · ')}
          </p>
          <div className="flex gap-3 mt-1">
            {job.salary_min_inr && (
              <span className="text-xs text-green-700 font-semibold flex items-center gap-0.5">
                <IndianRupee className="w-3 h-3" />
                {(job.salary_min_inr / 1000).toFixed(0)}k–{((job.salary_max_inr ?? job.salary_min_inr * 1.3) / 1000).toFixed(0)}k/month
              </span>
            )}
            {job.experience_min_years === 0 && (
              <span className="text-xs text-blue-700 font-semibold">Fresher OK</span>
            )}
          </div>
        </div>
        <button onClick={() => setLanguage(v => v === 'hi' ? 'en' : 'hi')}
          className="min-h-11 px-3 border border-gray-200 rounded-lg text-xs font-semibold text-gray-700">
          {language === 'hi' ? 'English' : 'हिंदी'}
        </button>
      </div>
    </div>
  )

  // ── Step 1: Phone input ───────────────────────────────────────────────────
  if (step === 'phone') return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-white flex flex-col">
      <Header />
      <div className="flex-1 flex flex-col items-center justify-center px-5 py-8">
        <div className="w-full max-w-sm space-y-6">
          {!online && <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800 flex gap-2"><WifiOff className="w-4 h-4" />Internet unavailable. Your entries remain on this page.</div>}
          <div className="text-center">
            <div className="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Phone className="w-8 h-8 text-purple-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-900">Apply in 60 seconds</h2>
            <p className="text-gray-500 text-sm mt-1">60 सेकंड में आवेदन करें</p>
            <p className="text-xs text-gray-400 mt-1">Enter your mobile number — we'll send an OTP</p>
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              Mobile Number / मोबाइल नंबर
            </label>
            <div className="flex gap-2">
              <div className="flex items-center gap-1.5 px-3 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-700 font-semibold">
                🇮🇳 +91
              </div>
              <input
                type="tel"
                value={phone.replace('+91', '')}
                onChange={e => setPhone(e.target.value.replace(/\D/g, '').slice(0, 10))}
                placeholder="9876543210"
                inputMode="numeric"
                maxLength={10}
                className="flex-1 border border-gray-200 rounded-xl px-4 py-3 text-lg font-semibold
                           tracking-widest focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            {otpError && <p className="text-red-600 text-xs mt-2 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{otpError}</p>}
          </div>

          <button
            onClick={sendOtp}
            disabled={otpSending || phone.replace('+91', '').length < 10}
            className="w-full flex items-center justify-center gap-2 py-4 bg-purple-600
                       hover:bg-purple-700 text-white text-base font-bold rounded-2xl
                       transition disabled:opacity-50 shadow-lg shadow-purple-200"
          >
            {otpSending ? <Loader className="w-5 h-5 animate-spin" /> : <ChevronRight className="w-5 h-5" />}
            Send OTP — OTP भेजें
          </button>

          {job.whatsapp_apply_url && (
            <a href={job.whatsapp_apply_url} className="w-full min-h-12 flex items-center justify-center gap-2 bg-green-600 text-white font-bold rounded-2xl px-4">
              <MessageCircle className="w-5 h-5" /> Apply on WhatsApp
            </a>
          )}

          <p className="text-center text-xs text-gray-400">
            आपका डेटा सुरक्षित है। DPDP Act 2023 compliant.
          </p>
        </div>
      </div>
    </div>
  )

  // ── Step 2: OTP verification ──────────────────────────────────────────────
  if (step === 'otp') return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-white flex flex-col">
      <Header />
      <div className="flex-1 flex flex-col items-center justify-center px-5 py-8">
        <div className="w-full max-w-sm space-y-6">
          <div className="text-center">
            <h2 className="text-xl font-bold text-gray-900">Enter OTP</h2>
            <p className="text-sm text-gray-500 mt-1">
              Sent to {phone} — OTP भेजा गया
            </p>
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">6-Digit OTP</label>
            <input
              type="text"
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="______"
              inputMode="numeric"
              maxLength={6}
              className="w-full text-center text-4xl font-bold tracking-[0.5em] border border-gray-200
                         rounded-2xl px-4 py-4 focus:outline-none focus:ring-2 focus:ring-purple-400"
            />
            {otpError && <p className="text-red-600 text-xs mt-2 text-center">{otpError}</p>}
          </div>

          <button
            onClick={verifyOtp}
            disabled={otp.length < 6 || submitting}
            className="w-full flex items-center justify-center gap-2 py-4 bg-purple-600
                       hover:bg-purple-700 text-white text-base font-bold rounded-2xl
                       transition disabled:opacity-50"
          >
            {submitting ? <Loader className="w-5 h-5 animate-spin" /> : <Check className="w-5 h-5" />}
            Verify — सत्यापित करें
          </button>

          {countdown > 0 ? (
            <p className="text-center text-xs text-gray-400">Resend in {countdown}s</p>
          ) : (
            <button onClick={() => { setStep('phone'); setOtp('') }}
              className="w-full text-center text-sm text-purple-600 font-semibold">
              Resend OTP — दोबारा भेजें
            </button>
          )}
        </div>
      </div>
    </div>
  )

  // ── Step 3: 5-field application form ─────────────────────────────────────
  if (step === 'form') return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-white flex flex-col">
      <Header />

      {/* Progress bar */}
      <div className="h-1 bg-gray-100">
        <div className="h-1 bg-purple-500 w-2/3 transition-all" />
      </div>

      <div className="flex-1 px-5 py-6 max-w-sm mx-auto w-full space-y-5">
        <h2 className="font-bold text-gray-900 text-lg">Almost there! / लगभग हो गया!</h2>

        {submitError && (
          <div className="bg-red-50 text-red-700 text-sm px-4 py-3 rounded-xl border border-red-100 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />{submitError}
          </div>
        )}

        {/* Field 1: Name */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1.5">
            Full Name * / पूरा नाम *
          </label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Priya Sharma"
            autoFocus
            className="w-full border border-gray-200 rounded-xl px-4 py-3 text-base
                       focus:outline-none focus:ring-2 focus:ring-purple-400"
          />
        </div>

        {/* Field 2: Experience */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1.5">
            Experience / अनुभव
          </label>
          <div className="grid grid-cols-1 gap-2">
            {EXP_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setExpYears(opt.value)}
                className={`w-full text-left px-4 py-3 rounded-xl border text-sm font-medium transition
                  ${expYears === opt.value
                    ? 'bg-purple-600 text-white border-purple-600'
                    : 'border-gray-200 text-gray-700 hover:border-purple-300'}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Field 3: City */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1.5">
            Current City / वर्तमान शहर
          </label>
          <input
            value={city}
            onChange={e => setCity(e.target.value)}
            placeholder="Mumbai, Delhi, Bengaluru…"
            className="w-full border border-gray-200 rounded-xl px-4 py-3 text-base
                       focus:outline-none focus:ring-2 focus:ring-purple-400"
          />
        </div>

        {/* Source is normally supplied by the tracked link; ask only for direct/unknown traffic. */}
        {srcParam === 'other' && <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1.5">
            How did you find this job? / कहाँ से पता चला?
          </label>
          <div className="grid grid-cols-2 gap-2">
            {SOURCES.map(s => (
              <button
                key={s.value}
                onClick={() => setSource(s.value)}
                className={`px-3 py-2 rounded-xl border text-xs font-medium transition text-left
                  ${source === s.value
                    ? 'bg-purple-600 text-white border-purple-600'
                    : 'border-gray-200 text-gray-700 hover:border-purple-300'}`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>}

        {/* Field 5: Referral name (conditional on source=referral) */}
        {source === 'referral' && (
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1.5">
              Referred by / किसने बताया?
            </label>
            <input
              value={sourceDetail}
              onChange={e => setSourceDetail(e.target.value)}
              placeholder="Employee name"
              className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm
                         focus:outline-none focus:ring-2 focus:ring-purple-400"
            />
          </div>
        )}

        <button
          onClick={submitApplication}
          disabled={submitting || !name.trim()}
          className="w-full flex items-center justify-center gap-2 py-4 bg-purple-600
                     hover:bg-purple-700 text-white text-base font-bold rounded-2xl
                     transition disabled:opacity-50 shadow-lg shadow-purple-200"
        >
          {submitting ? <Loader className="w-5 h-5 animate-spin" /> : <ChevronRight className="w-5 h-5" />}
          Submit Application — आवेदन जमा करें
        </button>
      </div>
    </div>
  )

  // ── Step 4: Success ───────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-white flex flex-col">
      <Header />
      <div className="flex-1 flex flex-col items-center justify-center px-5 py-12 text-center">
        <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
          <CheckCircle2 className="w-10 h-10 text-green-600" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Application Submitted!</h2>
        <p className="text-green-700 font-semibold text-lg mb-1">आवेदन सफलतापूर्वक जमा हो गया! 🎉</p>
        <p className="text-gray-500 text-sm mt-3 max-w-xs">
          We'll review your application and contact you on WhatsApp within 2–3 working days.
        </p>
        <p className="text-gray-500 text-sm mt-1 max-w-xs">
          हम 2–3 कार्य दिवसों में WhatsApp पर संपर्क करेंगे।
        </p>
        {job && (
          <div className="mt-6 bg-purple-50 border border-purple-100 rounded-2xl px-6 py-4 text-sm text-purple-800 font-medium">
            📞 {phone}<br />
            💼 {job.title}{job.property_name ? ` — ${job.property_name}` : ''}
          </div>
        )}
        <div className="mt-6 w-full max-w-sm text-left border-t border-gray-200 pt-5">
          <h3 className="font-semibold text-gray-900">Optional documents / वैकल्पिक दस्तावेज़</h3>
          <p className="text-xs text-gray-500 mt-1">Your application is already submitted. Upload now or return later.</p>
          <div className="grid grid-cols-1 gap-2 mt-3">
            <label className="min-h-12 border border-gray-200 rounded-xl px-4 flex items-center justify-center gap-2 font-semibold text-sm cursor-pointer bg-white">
              <Upload className="w-4 h-4" /> Upload resume
              <input type="file" className="hidden" accept=".pdf,.docx,image/jpeg,image/png"
                disabled={uploading} onChange={e => e.target.files?.[0] && uploadDocument(e.target.files[0], 'RESUME')} />
            </label>
            <label className="min-h-12 border border-gray-200 rounded-xl px-4 flex items-center justify-center gap-2 font-semibold text-sm cursor-pointer bg-white">
              <Upload className="w-4 h-4" /> Upload certificate or ID
              <input type="file" className="hidden" accept=".pdf,.docx,image/jpeg,image/png"
                disabled={uploading} onChange={e => e.target.files?.[0] && uploadDocument(e.target.files[0], 'CERTIFICATE')} />
            </label>
          </div>
          {uploading && <p className="text-xs text-purple-700 mt-2">Uploading…</p>}
          {uploadMessage && <p className="text-xs text-gray-700 mt-2">{uploadMessage}</p>}
        </div>
        {trackingUrl && <a href={trackingUrl} className="mt-4 min-h-12 px-5 inline-flex items-center justify-center rounded-xl bg-gray-900 text-white font-semibold">Track application status</a>}
        <p className="text-xs text-gray-400 mt-6">
          All the best for your application! शुभकामनाएं! 🙏
        </p>
      </div>
    </div>
  )
}
