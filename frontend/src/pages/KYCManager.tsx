/**
 * KYC Manager — Feature 06 India
 * Aadhaar eKYC OTP · PAN Verification · DigiLocker Connect · FSSAI Upload
 *
 * Mobile-first layout for hospitality HR teams.
 * All identity data rules enforced at API layer; UI just orchestrates.
 */

import { apiClient } from '@/lib/api'
import {
AlertCircle,
BadgeCheck,
CheckCircle2,
ChevronDown,ChevronUp,
Copy,ExternalLink,
Eye,EyeOff,
FileText,
Key,
Link2,
Loader2,RefreshCw,
ShieldCheck,
Smartphone,
Upload,X,
} from 'lucide-react'
import React,{ useCallback,useRef,useState } from 'react'

// ─── Shared styles ────────────────────────────────────────────────────────────
const inp = 'w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white disabled:bg-gray-50 disabled:text-gray-400'
const btn = 'flex items-center justify-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 active:scale-95'
const btnGhost = 'flex items-center gap-2 px-4 py-2.5 border border-gray-200 text-gray-600 text-sm font-medium rounded-xl hover:bg-gray-50 transition active:scale-95'
const card = 'bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden'

// ─── Status badge ─────────────────────────────────────────────────────────────
function Badge({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok === null) return <span className="text-xs bg-gray-100 text-gray-500 px-2.5 py-1 rounded-full font-semibold">{label}</span>
  return ok
    ? <span className="text-xs bg-green-100 text-green-700 px-2.5 py-1 rounded-full font-semibold flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />{label}</span>
    : <span className="text-xs bg-red-100 text-red-700 px-2.5 py-1 rounded-full font-semibold">{label}</span>
}

// ─── Section wrapper ──────────────────────────────────────────────────────────
function Section({
  title, subtitle, icon, badge, children, defaultOpen = false,
}: {
  title: string; subtitle: string; icon: React.ReactNode
  badge?: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={card}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-gray-50/50 transition"
      >
        <div className="flex-shrink-0 w-9 h-9 bg-orange-50 rounded-xl flex items-center justify-center text-orange-500">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-gray-900 text-sm">{title}</p>
          <p className="text-xs text-gray-500 mt-0.5 truncate">{subtitle}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {badge}
          {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </button>
      {open && <div className="px-5 pb-5 border-t border-gray-50">{children}</div>}
    </div>
  )
}

function Alert({ type, children }: { type: 'error' | 'success' | 'info' | 'warn'; children: React.ReactNode }) {
  const styles = {
    error:   'bg-red-50 border-red-100 text-red-700',
    success: 'bg-green-50 border-green-100 text-green-700',
    info:    'bg-blue-50 border-blue-100 text-blue-700',
    warn:    'bg-amber-50 border-amber-100 text-amber-700',
  }
  return (
    <div className={`flex items-start gap-2 border rounded-xl px-4 py-3 text-xs ${styles[type]}`}>
      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
      <span>{children}</span>
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// 1. Aadhaar eKYC
// ═════════════════════════════════════════════════════════════════════════════
function AadhaarSection({ candidateId }: { candidateId: string }) {
  const [step, setStep]           = useState<'idle' | 'otp-sent' | 'verified'>('idle')
  const [aadhaar, setAadhaar]     = useState('')
  const [requestId, setRequestId] = useState('')
  const [otp, setOtp]             = useState('')
  const [result, setResult]       = useState<any>(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [showAadhaar, setShowAadhaar] = useState(false)

  const initiateOTP = async () => {
    if (!candidateId) return
    setError(''); setLoading(true)
    try {
      const r = await apiClient.post('/kyc/aadhaar/initiate', {
        aadhaar_number: aadhaar.replace(/\s/g, ''),
        candidate_id:   candidateId,
      })
      setRequestId(r.data.request_id)
      setStep('otp-sent')
      setAadhaar('') // clear — never keep in state
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  const verifyOTP = async () => {
    setError(''); setLoading(true)
    try {
      const r = await apiClient.post('/kyc/aadhaar/verify', {
        request_id:   requestId,
        otp,
        candidate_id: candidateId,
      })
      setResult(r.data)
      setStep('verified')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="pt-4 space-y-4">
      <Alert type="warn">
        Full Aadhaar number is sent to UIDAI (via Surepass) and immediately discarded.
        Only the last 4 digits are stored — UIDAI mandate.
      </Alert>

      {step === 'idle' && (
        <>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">
              12-digit Aadhaar Number
            </label>
            <div className="relative">
              <input
                type={showAadhaar ? 'text' : 'password'}
                value={aadhaar}
                onChange={e => setAadhaar(e.target.value.replace(/\D/g, '').slice(0, 12))}
                className={`${inp} pr-10 font-mono tracking-widest`}
                placeholder="XXXX XXXX XXXX"
                inputMode="numeric"
                maxLength={12}
              />
              <button
                type="button"
                onClick={() => setShowAadhaar(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showAadhaar ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1">{aadhaar.length}/12 digits entered</p>
          </div>
          <button
            onClick={initiateOTP}
            disabled={aadhaar.length !== 12 || !candidateId || loading}
            className={`${btn} w-full`}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Smartphone className="w-4 h-4" />}
            Send OTP to UIDAI-registered mobile
          </button>
        </>
      )}

      {step === 'otp-sent' && (
        <>
          <Alert type="info">
            OTP sent to the mobile number registered with UIDAI.
            Enter the 6-digit code below.
          </Alert>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">6-digit OTP</label>
            <input
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className={`${inp} font-mono text-xl tracking-[0.5em] text-center`}
              placeholder="• • • • • •"
              inputMode="numeric"
              maxLength={6}
            />
            <p className="text-xs text-gray-400 mt-1 text-center">
              Sandbox: use <code className="bg-gray-100 px-1 rounded">123456</code>
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStep('idle')} className={`${btnGhost} flex-1`}>
              <RefreshCw className="w-4 h-4" /> Resend
            </button>
            <button
              onClick={verifyOTP}
              disabled={otp.length !== 6 || loading}
              className={`${btn} flex-1`}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
              Verify OTP
            </button>
          </div>
        </>
      )}

      {step === 'verified' && result && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-600" />
            <p className="font-bold text-green-700">Aadhaar Verified</p>
            {result.sandbox && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">Sandbox</span>}
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div><p className="text-xs text-gray-500">Aadhaar (masked)</p><p className="font-mono font-bold">{result.aadhaar_masked}</p></div>
            <div><p className="text-xs text-gray-500">Name (UIDAI)</p><p className="font-medium">{result.name_from_uid}</p></div>
            <div><p className="text-xs text-gray-500">Gender</p><p className="font-medium">{result.gender}</p></div>
          </div>
        </div>
      )}

      {error && <Alert type="error">{error}</Alert>}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// 2. PAN Verification
// ═════════════════════════════════════════════════════════════════════════════
function PANSection({ candidateId }: { candidateId: string }) {
  const [pan, setPan]             = useState('')
  const [nameMatch, setNameMatch] = useState('')
  const [result, setResult]       = useState<any>(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')

  const verify = async () => {
    setError(''); setLoading(true)
    try {
      const r = await apiClient.post('/kyc/pan/verify', {
        pan_number:    pan.toUpperCase(),
        candidate_id:  candidateId,
        name_to_match: nameMatch || undefined,
      })
      setResult(r.data)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  const valid = /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan.toUpperCase())

  return (
    <div className="pt-4 space-y-4">
      <Alert type="info">
        Full PAN is sent to Surepass (India KYC provider) for verification.
        Only the masked form (ABCDE****F) is stored.
      </Alert>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-semibold text-gray-600 mb-1 block">PAN Number *</label>
          <input
            value={pan}
            onChange={e => setPan(e.target.value.toUpperCase().slice(0, 10))}
            className={`${inp} font-mono tracking-widest uppercase`}
            placeholder="ABCDE1234F"
            maxLength={10}
          />
          {pan.length === 10 && (
            <p className={`text-xs mt-1 ${valid ? 'text-green-600' : 'text-red-500'}`}>
              {valid ? '✓ Valid format' : '✗ Invalid format'}
            </p>
          )}
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-600 mb-1 block">
            Name to match (optional)
          </label>
          <input
            value={nameMatch}
            onChange={e => setNameMatch(e.target.value)}
            className={inp}
            placeholder="Candidate full name"
          />
        </div>
      </div>

      <button
        onClick={verify}
        disabled={!valid || !candidateId || loading}
        className={`${btn} w-full`}
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BadgeCheck className="w-4 h-4" />}
        Verify PAN
      </button>

      {result && (
        <div className={`rounded-xl p-4 border-2 space-y-2 ${result.verified ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
          <div className="flex items-center gap-2">
            {result.verified
              ? <CheckCircle2 className="w-5 h-5 text-green-600" />
              : <AlertCircle className="w-5 h-5 text-red-600" />}
            <p className={`font-bold ${result.verified ? 'text-green-700' : 'text-red-700'}`}>
              {result.verified ? 'PAN Verified' : 'Verification Failed'}
            </p>
            {result.sandbox && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">Sandbox</span>}
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div><p className="text-xs text-gray-500">PAN (masked)</p><p className="font-mono font-bold">{result.pan_masked}</p></div>
            <div><p className="text-xs text-gray-500">Name on PAN</p><p className="font-medium">{result.name_on_pan || '—'}</p></div>
            {nameMatch && (
              <div className="col-span-2">
                <p className="text-xs text-gray-500">Name match</p>
                <p className={`font-semibold ${result.name_match ? 'text-green-600' : 'text-red-600'}`}>
                  {result.name_match ? '✓ Names match' : '✗ Name mismatch'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {error && <Alert type="error">{error}</Alert>}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// 3. DigiLocker Connect
// ═════════════════════════════════════════════════════════════════════════════
function DigiLockerSection({ candidateId }: { candidateId: string }) {
  const [authUrl, setAuthUrl]   = useState('')
  const [state, setState]       = useState('')
  const [code, setCode]         = useState('')
  const [docs, setDocs]         = useState<any[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [step, setStep]         = useState<'init' | 'pending' | 'done'>('init')
  const [copied, setCopied]     = useState(false)

  const getAuthUrl = async () => {
    if (!candidateId) return
    setError(''); setLoading(true)
    try {
      const r = await apiClient.get(`/kyc/digilocker/auth-url?candidate_id=${candidateId}`)
      setAuthUrl(r.data.auth_url)
      setState(r.data.state)
      setStep('pending')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  const connectCallback = async () => {
    setError(''); setLoading(true)
    try {
      const r = await apiClient.post('/kyc/digilocker/callback', {
        code,
        state,
        candidate_id: candidateId,
      })
      setDocs(r.data.documents || [])
      setStep('done')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  const copyUrl = () => {
    navigator.clipboard.writeText(authUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="pt-4 space-y-4">
      <Alert type="info">
        DigiLocker connects to the candidate's government-issued documents
        (Aadhaar card, Driving Licence, etc.) via MeitY OAuth 2.0.
      </Alert>

      {step === 'init' && (
        <button
          onClick={getAuthUrl}
          disabled={!candidateId || loading}
          className={`${btn} w-full`}
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
          Generate DigiLocker Auth URL
        </button>
      )}

      {step === 'pending' && (
        <>
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-blue-700">Step 1 — Share this URL with the candidate</p>
            <div className="flex gap-2">
              <input value={authUrl} readOnly className={`${inp} flex-1 text-xs`} />
              <button onClick={copyUrl} className={btnGhost}>
                {copied ? <CheckCircle2 className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
              </button>
              <a href={authUrl} target="_blank" rel="noopener noreferrer" className={btnGhost}>
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-600 mb-1">Step 2 — Paste the authorization code</p>
            <p className="text-xs text-gray-400 mb-2">
              After the candidate authorizes, DigiLocker redirects back with a code.
            </p>
            <input
              value={code}
              onChange={e => setCode(e.target.value.trim())}
              className={`${inp} font-mono`}
              placeholder="Paste authorization code here"
            />
          </div>
          <button
            onClick={connectCallback}
            disabled={!code || loading}
            className={`${btn} w-full`}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Connect DigiLocker
          </button>
        </>
      )}

      {step === 'done' && docs.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-green-700">
            <CheckCircle2 className="w-5 h-5" />
            <p className="font-bold">{docs.length} document(s) imported</p>
          </div>
          {docs.map((d: any, i: number) => (
            <div key={i} className="bg-gray-50 rounded-xl p-3 flex items-center gap-3">
              <FileText className="w-5 h-5 text-orange-500 flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900 truncate">{d.doc_name}</p>
                <p className="text-xs text-gray-500">{d.doc_type} · Issuer: {d.issuer || 'UIDAI'}</p>
              </div>
              <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 ml-auto" />
            </div>
          ))}
        </div>
      )}

      {error && <Alert type="error">{error}</Alert>}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// 4. FSSAI Certificate Upload
// ═════════════════════════════════════════════════════════════════════════════
function FSSAICertSection({ candidateId }: { candidateId: string }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [certType, setCertType] = useState('BASIC_FOOD_HYGIENE')
  const [expiry, setExpiry]     = useState('')
  const [phone, setPhone]       = useState('')
  const [file, setFile]         = useState<File | null>(null)
  const [stage, setStage]       = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [msg, setMsg]           = useState('')
  const [error, setError]       = useState('')
  const [certId, setCertId]     = useState('')

  const CERT_TYPES = [
    { value: 'BASIC_FOOD_HYGIENE',      label: 'Basic Food Hygiene' },
    { value: 'FOSTAC',                  label: 'FoSTaC Training' },
    { value: 'FSSAI_LICENSE',           label: 'FSSAI License' },
    { value: 'ALCOHOL_LICENSE_FORM_FL', label: 'Alcohol License (FL)' },
  ]

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!expiry) return
    setError(''); setStage('uploading'); setMsg('Creating record…')

    try {
      const payload: any = {
        cert_type:    certType,
        expiry_date:  expiry,
        candidate_phone: phone || undefined,
      }
      if (candidateId) payload.candidate_id = candidateId
      if (file) {
        payload.filename     = file.name
        payload.content_type = file.type || 'application/pdf'
      }

      const { data: cert } = await apiClient.post('/fssai/certificates', payload)
      setCertId(cert.id)

      if (file && cert.upload) {
        setMsg('Uploading to S3 ap-south-1…')
        await fetch(cert.upload.upload_url, {
          method:  'PUT',
          headers: cert.upload.upload_headers || { 'Content-Type': file.type || 'application/pdf' },
          body:    file,
        })
        setMsg('Confirming upload…')
        await apiClient.patch(`/fssai/certificates/${cert.id}/confirm-upload`, {
          s3_key: cert.upload.s3_key,
        })
      }

      setStage('done')
      setMsg(file ? 'Certificate uploaded successfully' : 'Certificate record created')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
      setStage('error')
    }
  }

  return (
    <div className="pt-4 space-y-4">
      <Alert type="info">
        Certificate files are stored in AWS S3 ap-south-1 (Mumbai) for India data localisation.
      </Alert>

      {stage === 'done' ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center space-y-2">
          <CheckCircle2 className="w-8 h-8 text-green-600 mx-auto" />
          <p className="font-bold text-green-700">{msg}</p>
          <p className="text-xs text-gray-500">Certificate ID: {certId.slice(0, 8).toUpperCase()}</p>
          <button onClick={() => { setStage('idle'); setFile(null); setExpiry('') }} className={btnGhost}>
            <RefreshCw className="w-4 h-4" /> Add another
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Certificate Type *</label>
              <select value={certType} onChange={e => setCertType(e.target.value)} className={inp}>
                {CERT_TYPES.map(ct => (
                  <option key={ct.value} value={ct.value}>{ct.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Expiry Date *</label>
              <input type="date" value={expiry} onChange={e => setExpiry(e.target.value)}
                className={inp} required min={new Date().toISOString().split('T')[0]} />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-gray-600 mb-1 block">
                Candidate Phone (for expiry SMS alerts)
              </label>
              <input value={phone} onChange={e => setPhone(e.target.value)}
                className={inp} placeholder="+91XXXXXXXXXX" />
            </div>
          </div>

          {/* File drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition ${
              file ? 'border-orange-400 bg-orange-50' : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <Upload className={`w-6 h-6 mx-auto mb-2 ${file ? 'text-orange-500' : 'text-gray-400'}`} />
            {file ? (
              <div className="flex items-center justify-center gap-2">
                <span className="text-sm font-medium text-orange-700 truncate max-w-xs">{file.name}</span>
                <button type="button" onClick={ev => { ev.stopPropagation(); setFile(null); if (fileRef.current) fileRef.current.value = '' }}>
                  <X className="w-4 h-4 text-gray-400 hover:text-red-500" />
                </button>
              </div>
            ) : (
              <>
                <p className="text-sm text-gray-600">Drop PDF, JPG, or PNG here</p>
                <p className="text-xs text-gray-400 mt-1">Max 10 MB</p>
              </>
            )}
          </div>
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp"
            className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />

          {stage === 'uploading' && (
            <div className="flex items-center gap-2 bg-orange-50 text-orange-700 rounded-xl px-4 py-2.5 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" /> {msg}
            </div>
          )}

          {error && <Alert type="error">{error}</Alert>}

          <button type="submit" disabled={!expiry || stage === 'uploading'} className={`${btn} w-full`}>
            {stage === 'uploading'
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <FileText className="w-4 h-4" />}
            {file ? 'Upload Certificate' : 'Save Record'}
          </button>
        </form>
      )}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// KYC Status bar
// ═════════════════════════════════════════════════════════════════════════════
function KYCStatusBar({ candidateId }: { candidateId: string }) {
  const [status, setStatus] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    if (!candidateId) return
    setLoading(true)
    try {
      const r = await apiClient.get(`/kyc/status/${candidateId}`)
      setStatus(r.data)
    } catch { setStatus(null) }
    finally { setLoading(false) }
  }, [candidateId])

  React.useEffect(() => { fetchStatus() }, [fetchStatus])

  if (!candidateId) return null

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-bold text-gray-800">KYC Completion</p>
        <button onClick={fetchStatus} disabled={loading} className="text-gray-400 hover:text-gray-600">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {status ? (
        <div className="flex flex-wrap gap-2">
          <Badge ok={status.aadhaar_verified} label="Aadhaar" />
          <Badge ok={status.pan_verified}     label="PAN" />
          <Badge ok={status.kyc_complete}     label="KYC Complete" />
          <span className="text-xs text-gray-500 ml-auto self-center">
            {status.total_verified} verification(s)
          </span>
        </div>
      ) : (
        <p className="text-xs text-gray-400">Enter candidate ID above to load status</p>
      )}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// Main Page
// ═════════════════════════════════════════════════════════════════════════════
export default function KYCManager() {
  const [candidateId, setCandidateId] = useState('')

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">KYC Manager 🇮🇳</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Aadhaar eKYC · PAN · DigiLocker · FSSAI — DPDP Act 2023 compliant
        </p>
      </div>

      {/* Candidate ID — shared across all sections */}
      <div className="bg-orange-50 border border-orange-100 rounded-2xl p-4">
        <label className="text-xs font-bold text-orange-700 mb-1 block flex items-center gap-1">
          <Key className="w-3 h-3" /> Candidate ID (required for all operations)
        </label>
        <div className="flex gap-2">
          <input
            value={candidateId}
            onChange={e => setCandidateId(e.target.value.trim())}
            className={`${inp} flex-1 font-mono text-xs`}
            placeholder="Paste candidate UUID here"
          />
          {candidateId && (
            <button onClick={() => setCandidateId('')} className="text-gray-400 hover:text-red-400">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        {candidateId && (
          <p className="text-xs text-orange-600 mt-1">
            ✓ Using candidate: {candidateId.slice(0, 8)}…
          </p>
        )}
      </div>

      {/* KYC status summary */}
      <KYCStatusBar candidateId={candidateId} />

      {/* Sections */}
      <Section
        title="Aadhaar eKYC"
        subtitle="OTP-based UIDAI verification · Aadhaar Act 2016"
        icon={<ShieldCheck className="w-5 h-5" />}
        badge={<Badge ok={null} label="Aadhaar" />}
        defaultOpen={true}
      >
        <AadhaarSection candidateId={candidateId} />
      </Section>

      <Section
        title="PAN Verification"
        subtitle="Income Tax Act 1961 · Stored masked only"
        icon={<BadgeCheck className="w-5 h-5" />}
        badge={<Badge ok={null} label="PAN" />}
      >
        <PANSection candidateId={candidateId} />
      </Section>

      <Section
        title="DigiLocker Connect"
        subtitle="Government document vault · MeitY OAuth 2.0"
        icon={<Link2 className="w-5 h-5" />}
      >
        <DigiLockerSection candidateId={candidateId} />
      </Section>

      <Section
        title="FSSAI Certificate"
        subtitle="Food Safety and Standards Act 2006 · S3 ap-south-1"
        icon={<FileText className="w-5 h-5" />}
      >
        <FSSAICertSection candidateId={candidateId} />
      </Section>
    </div>
  )
}
