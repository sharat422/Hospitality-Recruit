/**
 * IndiaComplianceCenter
 *
 * Feature 06 India — replaces Western compliance pages
 * (RTWManager, ComplianceCenter, DataPrivacyCenter, DEIDashboard).
 *
 * Tabs:
 *   Identity    Aadhaar / PAN / DigiLocker verification
 *   FSSAI       Food Safety certificates (hospitality-critical)
 *   EPF / ESIC  Social security registrations
 *   DPDP        Digital Personal Data Protection Act 2023
 *   Wages       Minimum wage compliance checker
 *   Working Hrs Working hours violation checker
 *   Prof. Tax   Professional tax calculator
 *   Diversity   SC / ST / OBC / PWD voluntary data
 *   Audit Log   India compliance audit trail
 */

import { apiClient } from '@/lib/api'
import {
AlertCircle,
Award,
BadgeCheck,
BarChart2,
Building2,
Check,
CheckCircle2,
Clock,
Download,
FileText,IndianRupee,
Loader2,
Lock,
RefreshCw,
ScrollText,
ShieldCheck,
Upload,
Users,
X
} from 'lucide-react'
import React,{ useCallback,useEffect,useRef,useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function fmtINR(n: number) {
  if (!n) return '₹0'
  const s = Math.floor(n).toString()
  if (s.length <= 3) return `₹${s}`
  const last3 = s.slice(-3)
  let rest = s.slice(0, -3)
  const g: string[] = []
  while (rest.length > 2) { g.unshift(rest.slice(-2)); rest = rest.slice(0, -2) }
  if (rest) g.unshift(rest)
  return `₹${g.join(',')},${last3}`
}

const inp = 'w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white'
const btn = 'flex items-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 active:scale-95'

function SectionCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gradient-to-r from-orange-50 to-amber-50">
        {icon}
        <h2 className="font-bold text-gray-800">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function ResultBox({ data, error }: { data: unknown; error: string }) {
  if (error) return (
    <div className="mt-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700 flex gap-2">
      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />{error}
    </div>
  )
  if (!data) return null
  return (
    <pre className="mt-3 bg-gray-50 border border-gray-200 rounded-xl p-4 text-xs overflow-x-auto whitespace-pre-wrap">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Identity Verification
// ─────────────────────────────────────────────────────────────────────────────

function IdentityTab() {
  const [cid, setCid]         = useState('')
  const [docType, setDocType] = useState('AADHAAR')
  const [pan, setPan]         = useState('')
  const [last4, setLast4]     = useState('')
  const [expiry, setExpiry]   = useState('')
  const [saving, setSaving]   = useState(false)
  const [result, setResult]   = useState<unknown>(null)
  const [error, setError]     = useState('')
  const [records, setRecords] = useState<unknown[]>([])

  const fetchRecords = async () => {
    if (!cid) return
    try {
      const r = await apiClient.get(`/india-compliance/identity-verification/${cid}`)
      setRecords(r.data)
    } catch { setRecords([]) }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setSaving(true)
    try {
      const r = await apiClient.post('/india-compliance/identity-verification', {
        candidate_id:    cid,
        doc_type:        docType,
        aadhaar_last4:   docType === 'AADHAAR' ? last4 : undefined,
        pan_number:      docType === 'PAN' ? pan : undefined,
        doc_expiry_date: expiry || undefined,
      })
      setResult(r.data)
      setPan('')
      setLast4('')
      fetchRecords()
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setSaving(false) }
  }

  return (
    <div className="space-y-6">
      <SectionCard title="Submit Identity Document" icon={<BadgeCheck className="w-5 h-5 text-orange-500" />}>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Candidate ID *</label>
              <input value={cid} onChange={e => setCid(e.target.value)} className={inp} placeholder="UUID" required />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Document Type</label>
              <select value={docType} onChange={e => setDocType(e.target.value)} className={inp}>
                {['AADHAAR','PAN','DIGILOCKER','VOTER_ID','PASSPORT','DRIVING_LICENCE'].map(t => (
                  <option key={t} value={t}>{t.replace('_',' ')}</option>
                ))}
              </select>
            </div>
            {docType === 'AADHAAR' && (
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1 block">Last 4 digits only *</label>
                <input value={last4} onChange={e => setLast4(e.target.value)} maxLength={4}
                  className={inp} placeholder="e.g. 4321" pattern="\d{4}" required />
                <p className="text-xs text-amber-600 mt-1">⚠️ Full Aadhaar must not be stored (UIDAI mandate)</p>
              </div>
            )}
            {docType === 'PAN' && (
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1 block">PAN Number *</label>
                <input value={pan} onChange={e => setPan(e.target.value.toUpperCase())} maxLength={10}
                  className={`${inp} font-mono`} placeholder="ABCDE1234F" required />
              </div>
            )}
            {['PASSPORT','DRIVING_LICENCE'].includes(docType) && (
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1 block">Expiry Date</label>
                <input type="date" value={expiry} onChange={e => setExpiry(e.target.value)} className={inp} />
              </div>
            )}
          </div>
          <button type="submit" disabled={saving} className={btn}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Submit Document
          </button>
        </form>
        <ResultBox data={result} error={error} />
      </SectionCard>

      <SectionCard title="Lookup Verifications" icon={<ScrollText className="w-5 h-5 text-orange-500" />}>
        <div className="flex gap-3">
          <input value={cid} onChange={e => setCid(e.target.value)} className={`${inp} flex-1`} placeholder="Candidate UUID" />
          <button onClick={fetchRecords} className={btn}><RefreshCw className="w-4 h-4" /> Fetch</button>
        </div>
        {records.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>{['Type','Status','PAN','Expiry','Created'].map(h => (
                  <th key={h} className="text-left px-3 py-2 text-xs text-gray-500 font-semibold">{h}</th>
                ))}</tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {(records as any[]).map(r => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium">{r.doc_type}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                        r.status === 'VERIFIED' ? 'bg-green-100 text-green-700' :
                        r.status === 'REJECTED' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
                      }`}>{r.status}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{r.pan_masked ?? '—'}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{r.doc_expiry_date ?? '—'}</td>
                    <td className="px-3 py-2 text-xs text-gray-400">
                      {new Date(r.created_at).toLocaleDateString('en-IN')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: FSSAI — Certificate tracking + S3 file upload
// ─────────────────────────────────────────────────────────────────────────────

type UploadStage = 'idle' | 'uploading-to-s3' | 'confirming' | 'done' | 'error'

const CERT_TYPES = [
  { value: 'BASIC_FOOD_HYGIENE',       label: 'Basic Food Hygiene' },
  { value: 'FOSTAC',                   label: 'FoSTaC Training' },
  { value: 'FSSAI_LICENSE',            label: 'FSSAI License (Establishment)' },
  { value: 'ALCOHOL_LICENSE_FORM_FL',  label: 'Alcohol License (Form FL)' },
]

const TRAINING_TYPES = new Set(['BASIC_FOOD_HYGIENE', 'FOSTAC'])


function expiryColor(daysLeft: number) {
  if (daysLeft < 0)  return 'text-red-700 font-bold'
  if (daysLeft < 7)  return 'text-red-600 font-bold'
  if (daysLeft < 30) return 'text-amber-600 font-medium'
  return 'text-gray-600'
}

function FSSAITab() {
  const fileRef = useRef<HTMLInputElement>(null)

  const [certs, setCerts]         = useState<any[]>([])
  const [expiring, setExpiring]   = useState<any[]>([])
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState('')

  // Upload state per newly created cert
  const [uploadStage, setUploadStage] = useState<UploadStage>('idle')
  const [uploadMsg, setUploadMsg]     = useState('')
  const [_uploadedCertId, setUploadedCertId] = useState<string | null>(null)

  const [form, setForm] = useState({
    cert_type:       'BASIC_FOOD_HYGIENE',
    candidate_id:    '',
    license_number:  '',
    license_type:    'BASIC',
    licensed_entity: '',
    activity_category: 'Restaurant',
    fostac_course:   'BASIC_HYGIENE',
    training_provider: '',
    alcohol_license_number: '',
    alcohol_license_form: 'FL-3',
    issuing_authority: '',
    issue_date:      '',
    expiry_date:     '',
    state_code:      '',
    candidate_phone: '',
    recruiter_email: '',
  })

  const [file, setFile] = useState<File | null>(null)

  const reload = useCallback(() => {
    apiClient.get('/fssai/certificates').then(r => setCerts(r.data)).catch(() => {})
    apiClient.get('/fssai/certificates/expiring?days=60').then(r => setExpiring(r.data)).catch(() => {})
  }, [])

  useEffect(() => { reload() }, [reload])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setFile(f)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    setUploadStage('idle')
    setUploadMsg('')

    try {
      // Step 1: Create cert record (+ get presigned URL if file selected)
      const payload: any = { ...form }
      if (file) {
        payload.filename     = file.name
        payload.content_type = file.type || 'application/pdf'
      }

      const { data: cert } = await apiClient.post('/fssai/certificates', payload)
      const certId = cert.id

      // Step 2: PUT file directly to S3 if we got a presigned URL
      if (file && cert.upload) {
        setUploadStage('uploading-to-s3')
        setUploadMsg('Uploading to S3 (ap-south-1)…')

        await fetch(cert.upload.upload_url, {
          method:  'PUT',
          headers: { 'Content-Type': file.type || 'application/pdf' },
          body:    file,
        })

        // Step 3: Confirm upload
        setUploadStage('confirming')
        setUploadMsg('Confirming upload…')
        await apiClient.patch(`/fssai/certificates/${certId}/confirm-upload`, {
          s3_key: cert.upload.s3_key,
        })

        setUploadStage('done')
        setUploadMsg('Certificate file uploaded successfully')
        setUploadedCertId(certId)
      }

      setCerts(prev => [cert, ...prev])
      reload()
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
      setUploadStage('error')
    } finally {
      setSaving(false)
    }
  }

  const isTraining = TRAINING_TYPES.has(form.cert_type)
  const isAlcohol  = form.cert_type === 'ALCOHOL_LICENSE_FORM_FL'

  return (
    <div className="space-y-6">

      {/* Expiry alerts banner */}
      {expiring.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4">
          <p className="font-semibold text-red-700 mb-2 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {expiring.length} FSSAI certificate(s) expiring within 60 days
          </p>
          <div className="space-y-1">
            {expiring.map((c: any) => {
              const dl = Math.floor((new Date(c.expiry_date).getTime() - Date.now()) / 86400000)
              return (
                <div key={c.id} className="flex items-center gap-2 text-sm text-red-600">
                  <span className={`w-2 h-2 rounded-full ${dl < 7 ? 'bg-red-600' : 'bg-amber-500'}`} />
                  <span className="font-medium">{c.cert_type.replace(/_/g, ' ')}</span>
                  <span className="text-gray-500">·</span>
                  <span>{c.license_number ?? c.fostac_cert_number ?? '—'}</span>
                  <span className="text-gray-500">· expires</span>
                  <span className="font-semibold">{c.expiry_date}</span>
                  <span className={`ml-auto text-xs px-2 py-0.5 rounded-full font-semibold ${dl < 7 ? 'bg-red-100' : 'bg-amber-100 text-amber-700'}`}>
                    {dl < 0 ? 'EXPIRED' : `${dl}d left`}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Add certificate form */}
      <SectionCard title="Add FSSAI Certificate" icon={<FileText className="w-5 h-5 text-orange-500" />}>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

            {/* Certificate type */}
            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Certificate Type *</label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {CERT_TYPES.map(ct => (
                  <button key={ct.value} type="button"
                    onClick={() => setForm(f => ({ ...f, cert_type: ct.value }))}
                    className={`px-3 py-2 rounded-xl border text-xs font-medium transition text-left ${
                      form.cert_type === ct.value
                        ? 'border-orange-500 bg-orange-50 text-orange-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}>
                    {ct.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Training-type fields */}
            {isTraining && (
              <>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Candidate ID (UUID)</label>
                  <input value={form.candidate_id} onChange={e => setForm(f => ({...f, candidate_id: e.target.value}))} className={inp} placeholder="e.g. cand-uuid" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Training Course</label>
                  <select value={form.fostac_course} onChange={e => setForm(f => ({...f, fostac_course: e.target.value}))} className={inp}>
                    <option value="BASIC_HYGIENE">Basic Hygiene</option>
                    <option value="FOOD_SAFETY_SUPERVISOR">Food Safety Supervisor</option>
                    <option value="ADVANCED_HYGIENE">Advanced Hygiene</option>
                    <option value="REFRESHER">Refresher</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Training Provider</label>
                  <input value={form.training_provider} onChange={e => setForm(f => ({...f, training_provider: e.target.value}))} className={inp} placeholder="FSSAI-approved centre name" />
                </div>
              </>
            )}

            {/* FSSAI License fields */}
            {form.cert_type === 'FSSAI_LICENSE' && (
              <>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">FSSAI License No. (14 digits) *</label>
                  <input value={form.license_number} onChange={e => setForm(f => ({...f, license_number: e.target.value}))} className={`${inp} font-mono`} placeholder="12345678901234" maxLength={14} required />
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">License Type</label>
                  <select value={form.license_type} onChange={e => setForm(f => ({...f, license_type: e.target.value}))} className={inp}>
                    <option value="BASIC">Basic (Petty food business)</option>
                    <option value="STATE">State License</option>
                    <option value="CENTRAL">Central License</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Licensed Entity Name</label>
                  <input value={form.licensed_entity} onChange={e => setForm(f => ({...f, licensed_entity: e.target.value}))} className={inp} placeholder="Hotel / Restaurant name" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Activity Category</label>
                  <select value={form.activity_category} onChange={e => setForm(f => ({...f, activity_category: e.target.value}))} className={inp}>
                    {['Restaurant','Hotel','Catering','Bakery','Cloud Kitchen','Canteen','Manufacturer','Retailer'].map(a => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                  </select>
                </div>
              </>
            )}

            {/* Alcohol license fields */}
            {isAlcohol && (
              <>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Alcohol License No.</label>
                  <input value={form.alcohol_license_number} onChange={e => setForm(f => ({...f, alcohol_license_number: e.target.value}))} className={`${inp} font-mono`} placeholder="License number" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">License Form</label>
                  <select value={form.alcohol_license_form} onChange={e => setForm(f => ({...f, alcohol_license_form: e.target.value}))} className={inp}>
                    <option value="FL-3">FL-3 (Retail)</option>
                    <option value="FL-11">FL-11 (Bar / Restaurant)</option>
                    <option value="FL-12">FL-12 (Club)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-600 mb-1 block">Issuing Authority</label>
                  <input value={form.issuing_authority} onChange={e => setForm(f => ({...f, issuing_authority: e.target.value}))} className={inp} placeholder="State Excise Department" />
                </div>
              </>
            )}

            {/* Common fields */}
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">State Code</label>
              <input value={form.state_code} onChange={e => setForm(f => ({...f, state_code: e.target.value.toUpperCase()}))} className={inp} placeholder="MH / KA / DL" maxLength={2} />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Issue Date</label>
              <input type="date" value={form.issue_date} onChange={e => setForm(f => ({...f, issue_date: e.target.value}))} className={inp} />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Expiry Date *</label>
              <input type="date" value={form.expiry_date} onChange={e => setForm(f => ({...f, expiry_date: e.target.value}))} className={inp} required />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Candidate Phone (for SMS alerts)</label>
              <input value={form.candidate_phone} onChange={e => setForm(f => ({...f, candidate_phone: e.target.value}))} className={inp} placeholder="+91XXXXXXXXXX" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Recruiter Email (for alerts)</label>
              <input type="email" value={form.recruiter_email} onChange={e => setForm(f => ({...f, recruiter_email: e.target.value}))} className={inp} placeholder="recruiter@hotel.in" />
            </div>

            {/* File upload */}
            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-gray-600 mb-1 block">
                Certificate Document (PDF/JPG/PNG — max 10 MB, stored in S3 ap-south-1)
              </label>
              <div
                onClick={() => fileRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-4 cursor-pointer transition flex items-center gap-3 ${
                  file ? 'border-orange-400 bg-orange-50' : 'border-gray-200 hover:border-gray-300'
                }`}>
                <Upload className={`w-5 h-5 flex-shrink-0 ${file ? 'text-orange-500' : 'text-gray-400'}`} />
                <span className="text-sm text-gray-600 flex-1 min-w-0 truncate">
                  {file ? file.name : 'Click to select PDF, JPG, or PNG'}
                </span>
                {file && (
                  <button type="button" onClick={ev => { ev.stopPropagation(); setFile(null); if (fileRef.current) fileRef.current.value = '' }}
                    className="text-gray-400 hover:text-red-500 flex-shrink-0">
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden" onChange={handleFileChange} />
              {file && <p className="text-xs text-gray-400 mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB · {file.type}</p>}
            </div>

          </div>

          {/* Upload progress */}
          {uploadStage !== 'idle' && uploadStage !== 'error' && (
            <div className={`flex items-center gap-2 text-sm px-4 py-2.5 rounded-xl ${
              uploadStage === 'done' ? 'bg-green-50 text-green-700' : 'bg-orange-50 text-orange-700'
            }`}>
              {uploadStage === 'done'
                ? <CheckCircle2 className="w-4 h-4" />
                : <Loader2 className="w-4 h-4 animate-spin" />}
              {uploadMsg}
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 text-sm text-red-700">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
            </div>
          )}

          <button type="submit" disabled={saving} className={btn}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
            {file ? 'Add Certificate & Upload File' : 'Add Certificate'}
          </button>
        </form>
      </SectionCard>

      {/* Certificate table */}
      <SectionCard
        title={`All FSSAI Certificates (${certs.length})`}
        icon={<BadgeCheck className="w-5 h-5 text-orange-500" />}>
        {certs.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">No certificates yet. Add one above.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {['Type', 'License / Cert No.', 'Entity / Course', 'Expiry', 'File', 'Status'].map(h => (
                    <th key={h} className="text-left px-3 py-2.5 text-xs text-gray-500 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {certs.map((c: any) => {
                  const daysLeft = Math.floor((new Date(c.expiry_date).getTime() - Date.now()) / 86400000)
                  return (
                    <tr key={c.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2.5">
                        <span className="inline-flex items-center gap-1 text-xs font-semibold bg-orange-50 text-orange-700 px-2 py-0.5 rounded-full">
                          {c.cert_type.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-gray-700">
                        {c.license_number ?? c.fostac_cert_number ?? c.alcohol_license_number ?? '—'}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-gray-600 max-w-[160px] truncate">
                        {c.licensed_entity ?? c.fostac_course?.replace(/_/g, ' ') ?? c.activity_category ?? '—'}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={`text-xs ${expiryColor(daysLeft)}`}>
                          {c.expiry_date}
                          <span className="ml-1">
                            {daysLeft < 0 ? '⚠ EXPIRED' : `(${daysLeft}d)`}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        {c.doc_url ? (
                          <a href={c.doc_url} target="_blank" rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">
                            <Download className="w-3 h-3" /> View
                          </a>
                        ) : (
                          <span className="text-xs text-gray-400">No file</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                          c.status === 'ACTIVE'         ? 'bg-green-100 text-green-700' :
                          c.status === 'RENEWAL_PENDING'? 'bg-amber-100 text-amber-700' :
                          'bg-red-100 text-red-700'
                        }`}>{c.status}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: EPF / ESIC
// ─────────────────────────────────────────────────────────────────────────────

function EPFESICTab() {
  const [calc, setCalc]   = useState({ basic_da: '', gross: '' })
  const [result, setResult] = useState<unknown>(null)
  const [error, setError]   = useState('')

  const calculate = async () => {
    setError('')
    try {
      const r = await apiClient.post('/india-compliance/epf-esic/contribution-calc', {
        monthly_basic_da_inr: parseFloat(calc.basic_da) || 0,
      })
      setResult(r.data)
    } catch (err: any) { setError(err.response?.data?.detail ?? err.message) }
  }

  const r = result as any
  return (
    <div className="space-y-6">
      <SectionCard title="EPF / ESIC Contribution Calculator" icon={<IndianRupee className="w-5 h-5 text-orange-500" />}>
        <p className="text-sm text-gray-500 mb-4">
          EPF: 12% employee + 12% employer (8.33% EPS + 3.67% EPF) on Basic+DA up to ₹15,000 ceiling.<br/>
          ESIC: 0.75% employee + 3.25% employer — applicable when gross ≤ ₹21,000/month.
        </p>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Monthly Basic+DA (₹)</label>
            <input type="number" value={calc.basic_da} onChange={e => setCalc(c => ({...c, basic_da: e.target.value}))} className={inp} placeholder="e.g. 12000" />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Monthly Gross Salary (₹) — for ESIC</label>
            <input type="number" value={calc.gross} onChange={e => setCalc(c => ({...c, gross: e.target.value}))} className={inp} placeholder="e.g. 18000" />
          </div>
        </div>
        <button onClick={calculate} className={btn}><IndianRupee className="w-4 h-4" /> Calculate</button>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        {r && (
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div className="bg-blue-50 rounded-xl p-4">
              <p className="text-xs font-semibold text-blue-700 mb-2 uppercase tracking-wide">EPF</p>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-gray-600">Employee EPF</span><span className="font-bold">{fmtINR(r.epf?.employee_epf_inr)}</span></div>
                <div className="flex justify-between"><span className="text-gray-600">Employer EPF</span><span className="font-bold">{fmtINR(r.epf?.employer_epf_inr)}</span></div>
                <div className="flex justify-between"><span className="text-gray-600">Employer EPS</span><span className="font-bold">{fmtINR(r.epf?.employer_eps_inr)}</span></div>
                <div className="flex justify-between border-t pt-1 mt-1"><span className="font-semibold">Total EPF</span><span className="font-bold text-blue-700">{fmtINR(r.epf?.total_epf_inr)}</span></div>
              </div>
            </div>
            {r.gratuity_preview && (
              <div className="bg-green-50 rounded-xl p-4">
                <p className="text-xs font-semibold text-green-700 mb-2 uppercase tracking-wide">Gratuity (after 5 yrs)</p>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-gray-600">Formula</span><span className="text-xs text-gray-500">(15/26) × salary × years</span></div>
                  <div className="flex justify-between"><span className="text-gray-600">5-year gratuity</span><span className="font-bold text-green-700">{fmtINR(r.gratuity_preview?.gratuity_inr)}</span></div>
                  <div className="text-xs text-gray-400 mt-1">Cap: {fmtINR(2000000)}</div>
                </div>
              </div>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Key Thresholds" icon={<ScrollText className="w-5 h-5 text-orange-500" />}>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ['EPF Applicability', '≥ 20 employees'],['EPF Wage Ceiling', '₹15,000/month'],
            ['EPS Contribution', '8.33% of ₹15,000'],['ESIC Applicability', '≥ 10 employees'],
            ['ESIC Wage Ceiling', '₹21,000/month gross'],['Overtime Rate', '2× ordinary rate'],
            ['Gratuity', '5 years → 15 days/year'],['Gratuity Cap', '₹20,00,000'],
          ].map(([k,v]) => (
            <div key={k} className="bg-gray-50 rounded-xl p-3 flex justify-between items-center">
              <span className="text-gray-600">{k}</span><span className="font-semibold">{v}</span>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Working Hours Violation Checker
// ─────────────────────────────────────────────────────────────────────────────

function WorkingHoursTab() {
  const [form, setForm] = useState({
    shift_start:      '',
    shift_end:        '',
    break_hours:      '0.5',
    establishment_type: 'SHOP',
    is_female_worker: false,
    hourly_rate_inr:  '',
    prev_shift_end:   '',
    weekly_hours:     '',
  })
  const [shiftResult, setShiftResult]   = useState<any>(null)
  const [restResult, setRestResult]     = useState<any>(null)
  const [weeklyResult, setWeeklyResult] = useState<any>(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState('')

  const f = (k: string, v: string | boolean) => setForm(p => ({ ...p, [k]: v }))

  const checkAll = async () => {
    if (!form.shift_start || !form.shift_end) return
    setError(''); setLoading(true)
    setShiftResult(null); setRestResult(null); setWeeklyResult(null)
    try {
      const [s, r, w] = await Promise.all([
        // single shift check
        apiClient.post('/labour/working-hours/check', {
          shift_start:        form.shift_start,
          shift_end:          form.shift_end,
          break_hours:        parseFloat(form.break_hours) || 0.5,
          establishment_type: form.establishment_type,
          hourly_rate_inr:    parseFloat(form.hourly_rate_inr) || 0,
        }),
        // 12h rest check (only if prev_shift_end provided)
        form.prev_shift_end
          ? apiClient.post('/labour/working-hours/check-rest', {
              previous_shift_end:  form.prev_shift_end,
              current_shift_start: form.shift_start,
            })
          : Promise.resolve(null),
        // weekly hours check (only if weekly_hours provided)
        form.weekly_hours
          ? apiClient.post('/labour/working-hours/check-weekly', {
              weekly_actual_hours: parseFloat(form.weekly_hours),
              establishment_type:  form.establishment_type,
            })
          : Promise.resolve(null),
      ])
      setShiftResult(s.data)
      if (r) setRestResult(r.data)
      if (w) setWeeklyResult(w.data)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  const ViolationBadge = ({ violations }: { violations: any[] }) => {
    if (!violations?.length) return (
      <span className="text-xs bg-green-100 text-green-700 px-2.5 py-1 rounded-full font-semibold flex items-center gap-1">
        <Check className="w-3 h-3" /> Compliant
      </span>
    )
    return (
      <span className="text-xs bg-red-100 text-red-700 px-2.5 py-1 rounded-full font-semibold">
        {violations.length} violation{violations.length > 1 ? 's' : ''}
      </span>
    )
  }

  return (
    <div className="space-y-5">
      <SectionCard title="Shift Details" icon={<Clock className="w-5 h-5 text-orange-500" />}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Shift Start *</label>
            <input type="datetime-local" value={form.shift_start}
              onChange={e => f('shift_start', e.target.value)} className={inp} required />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Shift End *</label>
            <input type="datetime-local" value={form.shift_end}
              onChange={e => f('shift_end', e.target.value)} className={inp} required />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Break (hours)</label>
            <input type="number" step="0.5" min="0" value={form.break_hours}
              onChange={e => f('break_hours', e.target.value)} className={inp} />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Establishment Type</label>
            <select value={form.establishment_type} onChange={e => f('establishment_type', e.target.value)} className={inp}>
              <option value="SHOP">Shop / Hotel / Restaurant</option>
              <option value="FACTORY">Factory</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Hourly Rate (₹) — for OT pay</label>
            <input type="number" value={form.hourly_rate_inr}
              onChange={e => f('hourly_rate_inr', e.target.value)} className={inp} placeholder="e.g. 100" />
          </div>
          <div className="flex items-center gap-3 pt-5">
            <input type="checkbox" id="female" checked={form.is_female_worker}
              onChange={e => f('is_female_worker', e.target.checked)}
              className="w-4 h-4 accent-orange-500 rounded" />
            <label htmlFor="female" className="text-sm text-gray-700 cursor-pointer">
              Female worker (OSH Code 2020 s.43)
            </label>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Previous Shift End (for 12h rest check)</label>
            <input type="datetime-local" value={form.prev_shift_end}
              onChange={e => f('prev_shift_end', e.target.value)} className={inp} />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Weekly Hours So Far</label>
            <input type="number" value={form.weekly_hours}
              onChange={e => f('weekly_hours', e.target.value)} className={inp} placeholder="e.g. 36" />
          </div>
        </div>
        <button onClick={checkAll} disabled={!form.shift_start || !form.shift_end || loading} className={`${btn} mt-4`}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
          Check All Rules
        </button>
        {error && <p className="mt-3 text-sm text-red-600 bg-red-50 p-3 rounded-xl">{error}</p>}
      </SectionCard>

      {shiftResult && (
        <SectionCard title="Shift Analysis" icon={<Clock className="w-5 h-5 text-blue-500" />}>
          <div className="flex items-center gap-3 mb-4">
            <ViolationBadge violations={shiftResult.violations} />
            {shiftResult.is_overtime && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2.5 py-1 rounded-full font-semibold">
                Overtime ({shiftResult.overtime_hours}h)
              </span>
            )}
            {shiftResult.is_night_shift && (
              <span className="text-xs bg-purple-100 text-purple-700 px-2.5 py-1 rounded-full font-semibold">
                Night Shift
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-4">
            {[
              ['Actual Hours', `${shiftResult.actual_hours}h`],
              ['Spread Over',  `${shiftResult.spread_over_hours}h`],
              ['Overtime',     `${shiftResult.overtime_hours}h`],
              ['OT Pay',       shiftResult.overtime_inr ? fmtINR(shiftResult.overtime_inr) : '—'],
            ].map(([k,v]) => (
              <div key={k} className="bg-gray-50 rounded-xl p-3">
                <p className="text-xs text-gray-500 mb-0.5">{k}</p>
                <p className="font-bold text-gray-900">{v}</p>
              </div>
            ))}
          </div>
          {shiftResult.violations?.length > 0 && (
            <div className="space-y-2">
              {shiftResult.violations.map((v: any, i: number) => (
                <div key={i} className={`rounded-xl px-4 py-2.5 border text-sm ${
                  v.severity === 'HIGH' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-amber-50 border-amber-200 text-amber-700'
                }`}>
                  <p className="font-semibold">{v.type.replace(/_/g,' ')}</p>
                  <p className="text-xs mt-0.5">{v.message}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{v.law}</p>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      )}

      {restResult && (
        <SectionCard title="Rest Period Check (12h Rule)" icon={<Users className="w-5 h-5 text-purple-500" />}>
          <div className="flex items-center gap-3 mb-3">
            {restResult.compliant
              ? <span className="text-xs bg-green-100 text-green-700 px-2.5 py-1 rounded-full font-semibold"><Check className="inline w-3 h-3 mr-1" />Compliant</span>
              : <span className="text-xs bg-red-100 text-red-700 px-2.5 py-1 rounded-full font-semibold">Violation</span>}
            <span className="text-sm text-gray-600">Rest: <strong>{restResult.rest_hours}h</strong> (min {restResult.required_hours}h)</span>
          </div>
          {restResult.violation && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 text-sm text-red-700">
              <p className="font-semibold">{restResult.violation.message}</p>
              <p className="text-xs text-gray-500 mt-0.5">{restResult.violation.law}</p>
            </div>
          )}
        </SectionCard>
      )}

      {weeklyResult && (
        <SectionCard title="Weekly Hours Check" icon={<BarChart2 className="w-5 h-5 text-teal-500" />}>
          <div className="flex items-center gap-3 mb-3">
            {weeklyResult.compliant
              ? <span className="text-xs bg-green-100 text-green-700 px-2.5 py-1 rounded-full font-semibold">Compliant</span>
              : <span className="text-xs bg-red-100 text-red-700 px-2.5 py-1 rounded-full font-semibold">Over 48h limit</span>}
            <span className="text-sm text-gray-600">
              {weeklyResult.weekly_actual_hours}h / {weeklyResult.weekly_limit}h limit
            </span>
            {weeklyResult.is_overtime && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">OT: {weeklyResult.overtime_hours}h</span>}
          </div>
          <div className="bg-gray-100 rounded-full h-3 overflow-hidden">
            <div
              className={`h-3 rounded-full transition-all ${weeklyResult.compliant ? 'bg-green-500' : 'bg-red-500'}`}
              style={{ width: `${Math.min(100, (weeklyResult.weekly_actual_hours / weeklyResult.weekly_limit) * 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-2">{weeklyResult.law}</p>
        </SectionCard>
      )}

      <SectionCard title="Quick Reference" icon={<ScrollText className="w-5 h-5 text-orange-500" />}>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {[
            ['Standard daily', '8 hours'],['Max daily', '9 hours (hard cap)'],
            ['Overtime starts','After 8h'],['Spread-over limit', '10.5 hours'],
            ['Weekly max', '48 hours / week'],['Min shift rest', '12 hours between shifts'],
            ['OT rate', '2× ordinary rate'],['Night shift (women)', 'Written consent + transport required'],
          ].map(([k,v]) => (
            <div key={k} className="bg-gray-50 rounded-lg p-2.5 flex justify-between gap-2">
              <span className="text-gray-500 flex-shrink-0">{k}</span>
              <span className="font-semibold text-right">{v}</span>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: DPDP
// ─────────────────────────────────────────────────────────────────────────────

function DPDPTab() {
  const [purposes, setPurposes] = useState<{code:string;description:string}[]>([])
  const [requests, setRequests] = useState<unknown[]>([])
  const [consentForm, setConsentForm] = useState({ candidate_id: '', purpose_code: 'RECRUITMENT_DATA', consented: true })
  const [erasureForm, setErasureForm] = useState({ candidate_id: '', request_type: 'ERASURE', reason: '' })
  const [saving, setSaving]  = useState(false)
  const [result, setResult]  = useState<unknown>(null)
  const [error, setError]    = useState('')

  useEffect(() => {
    apiClient.get('/india-compliance/dpdp/purpose-codes').then(r => setPurposes(r.data)).catch(() => {})
    apiClient.get('/india-compliance/dpdp/erasure-requests').then(r => setRequests(r.data)).catch(() => {})
  }, [])

  const recordConsent = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setSaving(true)
    try {
      const r = await apiClient.post('/india-compliance/dpdp/consent', consentForm)
      setResult(r.data)
    } catch (err: any) { setError(err.response?.data?.detail ?? err.message) }
    finally { setSaving(false) }
  }

  const submitErasure = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setSaving(true)
    try {
      const r = await apiClient.post('/india-compliance/dpdp/erasure-request', erasureForm)
      setResult(r.data)
      setRequests(prev => [r.data, ...prev as any[]])
    } catch (err: any) { setError(err.response?.data?.detail ?? err.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-4">
        <p className="font-semibold text-blue-800 mb-1">Digital Personal Data Protection Act 2023</p>
        <p className="text-sm text-blue-700">
          Consent must be: free · specific · informed · unconditional · unambiguous.
          Response deadline: <strong>30 days</strong>. Data principal can withdraw consent at any time.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <SectionCard title="Record DPDP Consent" icon={<Check className="w-5 h-5 text-green-600" />}>
          <form onSubmit={recordConsent} className="space-y-3">
            <div><label className="text-xs font-semibold text-gray-600 mb-1 block">Candidate ID *</label>
              <input value={consentForm.candidate_id} onChange={e => setConsentForm(f => ({...f, candidate_id: e.target.value}))} className={inp} placeholder="UUID" required /></div>
            <div><label className="text-xs font-semibold text-gray-600 mb-1 block">Purpose</label>
              <select value={consentForm.purpose_code} onChange={e => setConsentForm(f => ({...f, purpose_code: e.target.value}))} className={inp}>
                {purposes.map(p => <option key={p.code} value={p.code}>{p.code}</option>)}
              </select>
              <p className="text-xs text-gray-500 mt-1">{purposes.find(p=>p.code===consentForm.purpose_code)?.description}</p>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" checked={consentForm.consented} onChange={e => setConsentForm(f => ({...f, consented: e.target.checked}))} className="accent-orange-500 w-4 h-4" />
              <label className="text-sm text-gray-700">Candidate consented</label>
            </div>
            <button type="submit" disabled={saving} className={btn}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              Record Consent
            </button>
          </form>
          <ResultBox data={result} error={error} />
        </SectionCard>

        <SectionCard title="Erasure / Correction Request" icon={<Lock className="w-5 h-5 text-red-500" />}>
          <form onSubmit={submitErasure} className="space-y-3">
            <div><label className="text-xs font-semibold text-gray-600 mb-1 block">Candidate ID *</label>
              <input value={erasureForm.candidate_id} onChange={e => setErasureForm(f => ({...f, candidate_id: e.target.value}))} className={inp} placeholder="UUID" required /></div>
            <div><label className="text-xs font-semibold text-gray-600 mb-1 block">Request Type</label>
              <select value={erasureForm.request_type} onChange={e => setErasureForm(f => ({...f, request_type: e.target.value}))} className={inp}>
                <option value="ERASURE">Erasure (Delete Data)</option>
                <option value="CORRECTION">Correction / Update</option>
                <option value="ACCESS">Access (Data Export)</option>
              </select>
            </div>
            <div><label className="text-xs font-semibold text-gray-600 mb-1 block">Reason</label>
              <textarea value={erasureForm.reason} onChange={e => setErasureForm(f => ({...f, reason: e.target.value}))} className={`${inp} resize-none`} rows={2} placeholder="Candidate's stated reason..." /></div>
            <button type="submit" disabled={saving} className={`${btn} bg-red-500 hover:bg-red-600`}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
              Submit Request
            </button>
          </form>
        </SectionCard>
      </div>

      <SectionCard title={`Erasure Requests (${requests.length})`} icon={<ScrollText className="w-5 h-5 text-orange-500" />}>
        {requests.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">No pending requests.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50"><tr>
              {['Type','Status','Requested','Due By'].map(h => (
                <th key={h} className="text-left px-3 py-2 text-xs text-gray-500 font-semibold">{h}</th>
              ))}
            </tr></thead>
            <tbody className="divide-y divide-gray-50">
              {(requests as any[]).map(r => {
                const due = new Date(r.response_due_at)
                const overdue = due < new Date() && r.status === 'PENDING'
                return (
                  <tr key={r.id} className={overdue ? 'bg-red-50' : 'hover:bg-gray-50'}>
                    <td className="px-3 py-2 font-medium">{r.request_type}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                        r.status === 'COMPLETED' ? 'bg-green-100 text-green-700' :
                        r.status === 'REJECTED' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                      }`}>{r.status}</span>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500">{new Date(r.requested_at).toLocaleDateString('en-IN')}</td>
                    <td className="px-3 py-2 text-xs">
                      <span className={overdue ? 'text-red-600 font-bold' : 'text-gray-600'}>
                        {due.toLocaleDateString('en-IN')} {overdue ? '⚠️ OVERDUE' : ''}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Minimum Wages
// ─────────────────────────────────────────────────────────────────────────────

function WagesTab() {
  const [wages, setWages]   = useState<unknown[]>([])
  const [state, setState]   = useState('MH')
  const [skill, setSkill]   = useState('UNSKILLED')
  const [offered, setOffered] = useState('')
  const [checkResult, setCheckResult] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    apiClient.get(`/india-compliance/minimum-wages?state_code=${state}`).then(r => setWages(r.data)).catch(() => {})
  }, [state])

  const checkWage = async () => {
    setLoading(true)
    try {
      const r = await apiClient.post('/india-compliance/minimum-wages/check', {
        state_code: state, skill_category: skill, offered_monthly_inr: parseFloat(offered),
      })
      setCheckResult(r.data)
    } catch { setCheckResult(null) }
    finally { setLoading(false) }
  }

  const cr = checkResult as any
  const STATES = [['MH','Maharashtra'],['DL','Delhi'],['KA','Karnataka'],['TN','Tamil Nadu'],['GA','Goa'],['RJ','Rajasthan'],['KL','Kerala'],['WB','West Bengal'],['TS','Telangana'],['UP','Uttar Pradesh']]

  return (
    <div className="space-y-6">
      <SectionCard title="Minimum Wage Compliance Check" icon={<IndianRupee className="w-5 h-5 text-orange-500" />}>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">State</label>
            <select value={state} onChange={e => setState(e.target.value)} className={inp}>
              {STATES.map(([c,n]) => <option key={c} value={c}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Skill Category</label>
            <select value={skill} onChange={e => setSkill(e.target.value)} className={inp}>
              {['UNSKILLED','SEMI_SKILLED','SKILLED','HIGHLY_SKILLED'].map(s => (
                <option key={s} value={s}>{s.replace('_',' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Offered Monthly (₹)</label>
            <input type="number" value={offered} onChange={e => setOffered(e.target.value)} className={inp} placeholder="e.g. 15000" />
          </div>
        </div>
        <button onClick={checkWage} disabled={loading || !offered} className={btn}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
          Check Compliance
        </button>

        {cr && (
          <div className={`mt-4 p-4 rounded-xl border-2 ${cr.compliant ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'}`}>
            <p className={`font-bold text-lg ${cr.compliant ? 'text-green-700' : 'text-red-700'}`}>
              {cr.compliant ? '✓ Compliant' : '✗ Below Minimum Wage'}
            </p>
            <div className="mt-2 space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-gray-600">Offered</span><span className="font-bold">{fmtINR(cr.offered_monthly_inr)}/month</span></div>
              <div className="flex justify-between"><span className="text-gray-600">Minimum ({cr.state})</span><span className="font-bold">{fmtINR(cr.minimum_monthly_inr)}/month</span></div>
              {!cr.compliant && <div className="flex justify-between text-red-600"><span>Shortfall</span><span className="font-bold">{fmtINR(cr.shortfall_inr)}</span></div>}
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard title={`Current Rates — ${STATES.find(([c])=>c===state)?.[1]}`} icon={<ScrollText className="w-5 h-5 text-orange-500" />}>
        {wages.length === 0 ? <p className="text-sm text-gray-400 text-center py-4">No data.</p> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50"><tr>
              {['Category','Daily (₹)','Monthly (₹)','Zone','Since'].map(h => (
                <th key={h} className="text-left px-3 py-2 text-xs text-gray-500 font-semibold">{h}</th>
              ))}
            </tr></thead>
            <tbody className="divide-y divide-gray-50">
              {(wages as any[]).map(w => (
                <tr key={w.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium">{w.skill_category.replace('_',' ')}</td>
                  <td className="px-3 py-2 font-bold text-orange-600">{fmtINR(w.daily_wage_inr)}</td>
                  <td className="px-3 py-2 font-bold text-orange-600">{fmtINR(w.monthly_wage_inr)}</td>
                  <td className="px-3 py-2 text-gray-500">Zone {w.zone}</td>
                  <td className="px-3 py-2 text-xs text-gray-400">{w.effective_from}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Professional Tax
// ─────────────────────────────────────────────────────────────────────────────

function ProfTaxTab() {
  const [state, setState]   = useState('MH')
  const [salary, setSalary] = useState('')
  const [month, setMonth]   = useState(new Date().getMonth() + 1)
  const [result, setResult] = useState<unknown>(null)
  const [slabs, setSlabs]   = useState<unknown[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    apiClient.get(`/india-compliance/professional-tax/slabs?state_code=${state}`).then(r => setSlabs(r.data)).catch(() => {})
  }, [state])

  const calculate = async () => {
    setLoading(true)
    try {
      const r = await apiClient.post('/india-compliance/professional-tax/calculate', {
        state_code: state, monthly_salary_inr: parseFloat(salary), month,
      })
      setResult(r.data)
    } finally { setLoading(false) }
  }

  const PT_STATES = [['MH','Maharashtra'],['KA','Karnataka'],['WB','West Bengal'],['TN','Tamil Nadu'],['AP','Andhra Pradesh'],['TS','Telangana'],['KL','Kerala'],['MP','Madhya Pradesh']]
  const cr = result as any

  return (
    <div className="space-y-6">
      <SectionCard title="Professional Tax Calculator" icon={<Building2 className="w-5 h-5 text-orange-500" />}>
        <p className="text-sm text-gray-500 mb-4">Professional Tax is levied by state governments. Gujarat abolished it in 2023. Central govt. employees are exempt.</p>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">State</label>
            <select value={state} onChange={e => setState(e.target.value)} className={inp}>
              {PT_STATES.map(([c,n]) => <option key={c} value={c}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Monthly Gross Salary (₹)</label>
            <input type="number" value={salary} onChange={e => setSalary(e.target.value)} className={inp} placeholder="e.g. 25000" />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Month (for Feb surcharge)</label>
            <select value={month} onChange={e => setMonth(Number(e.target.value))} className={inp}>
              {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map((m,i) => (
                <option key={i+1} value={i+1}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        <button onClick={calculate} disabled={loading || !salary} className={btn}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <IndianRupee className="w-4 h-4" />}
          Calculate PT
        </button>

        {cr && (
          <div className="mt-4 bg-orange-50 border border-orange-200 rounded-xl p-4">
            {cr.applicable ? (
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Professional Tax ({cr.state_name})</p>
                  <p className="text-xs text-gray-400">Slab: {fmtINR(cr.slab_min_inr)} – {cr.slab_max_inr ? fmtINR(cr.slab_max_inr) : '∞'}</p>
                  {cr.is_february && <p className="text-xs text-amber-600">February surcharge applied</p>}
                </div>
                <p className="text-2xl font-bold text-orange-600">{fmtINR(cr.pt_inr)}<span className="text-sm font-normal text-gray-500">/month</span></p>
              </div>
            ) : (
              <p className="text-green-700 font-semibold">✓ Professional Tax not applicable in {cr.state_code}</p>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard title={`PT Slabs — ${PT_STATES.find(([c])=>c===state)?.[1]}`} icon={<ScrollText className="w-5 h-5 text-orange-500" />}>
        {slabs.length === 0 ? <p className="text-sm text-gray-400 text-center py-4">No slab data.</p> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50"><tr>
              {['Min Salary','Max Salary','PT/Month','Feb PT'].map(h => (
                <th key={h} className="text-left px-3 py-2 text-xs text-gray-500 font-semibold">{h}</th>
              ))}
            </tr></thead>
            <tbody className="divide-y divide-gray-50">
              {(slabs as any[]).map((s,i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-3 py-2">{fmtINR(s.slab_min_salary_inr)}</td>
                  <td className="px-3 py-2">{s.slab_max_salary_inr ? fmtINR(s.slab_max_salary_inr) : '& above'}</td>
                  <td className="px-3 py-2 font-bold text-orange-600">{fmtINR(s.pt_monthly_inr)}</td>
                  <td className="px-3 py-2 text-gray-500">{s.pt_february_inr ? fmtINR(s.pt_february_inr) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SectionCard>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab: Audit Log
// ─────────────────────────────────────────────────────────────────────────────

function AuditLogTab() {
  const [logs, setLogs]     = useState<unknown[]>([])
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState('')

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const url = action ? `/india-compliance/audit-log?action=${action}&limit=100` : '/india-compliance/audit-log?limit=100'
      const r = await apiClient.get(url)
      setLogs(r.data)
    } finally { setLoading(false) }
  }, [action])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <select value={action} onChange={e => setAction(e.target.value)} className={`${inp} w-64`}>
          <option value="">All Actions</option>
          {['IDENTITY_VERIFIED','IDENTITY_REJECTED','EPF_REGISTERED','DPDP_CONSENT_GIVEN','DPDP_CONSENT_WITHDRAWN','DPDP_ERASURE_REQUESTED','DPDP_ERASURE_COMPLETED','FSSAI_CERT_ADDED','DIVERSITY_DATA_COLLECTED','DATA_ANONYMISED','WORKING_HOURS_FLAGGED'].map(a => (
            <option key={a} value={a}>{a.replace(/_/g,' ')}</option>
          ))}
        </select>
        <button onClick={fetchLogs} className={btn}><RefreshCw className="w-4 h-4" /> Refresh</button>
      </div>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>
        ) : logs.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-10">No audit logs.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100"><tr>
                {['Action','Entity','Law Reference','Actor','Time'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs text-gray-500 font-semibold">{h}</th>
                ))}
              </tr></thead>
              <tbody className="divide-y divide-gray-50">
                {(logs as any[]).map(l => (
                  <tr key={l.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3"><span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-semibold">{l.action?.replace(/_/g,' ')}</span></td>
                    <td className="px-4 py-3 text-xs text-gray-600">{l.entity_type} {l.entity_id ? `· ${l.entity_id.slice(0,8)}…` : ''}</td>
                    <td className="px-4 py-3 text-xs text-blue-600">{l.law_reference ?? '—'}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">{l.actor_type}</td>
                    <td className="px-4 py-3 text-xs text-gray-400">{new Date(l.created_at).toLocaleString('en-IN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'identity', label: 'Identity',    icon: <ShieldCheck className="w-4 h-4" /> },
  { id: 'fssai',   label: 'FSSAI',        icon: <FileText className="w-4 h-4" /> },
  { id: 'epf',     label: 'EPF / ESIC',   icon: <IndianRupee className="w-4 h-4" /> },
  { id: 'hours',   label: 'Work Hours',   icon: <Clock className="w-4 h-4" /> },
  { id: 'dpdp',    label: 'DPDP',         icon: <Lock className="w-4 h-4" /> },
  { id: 'wages',   label: 'Min. Wages',   icon: <Award className="w-4 h-4" /> },
  { id: 'pt',      label: 'Prof. Tax',    icon: <Building2 className="w-4 h-4" /> },
  { id: 'audit',   label: 'Audit Log',    icon: <ScrollText className="w-4 h-4" /> },
]

export default function IndiaComplianceCenter() {
  const [tab, setTab] = useState('identity')

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">India Compliance Centre 🇮🇳</h1>
        <p className="text-sm text-gray-500 mt-1">
          DPDP Act 2023 · EPF/ESIC · FSSAI · Minimum Wages Act · Factories Act · Professional Tax
        </p>
      </div>

      {/* Tab bar — scrollable on mobile */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-6 overflow-x-auto scrollbar-hide">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition flex-shrink-0 ${
              tab === t.id ? 'bg-white text-orange-600 shadow-sm' : 'text-gray-600 hover:text-gray-800'
            }`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {tab === 'identity' && <IdentityTab />}
      {tab === 'fssai'   && <FSSAITab />}
      {tab === 'epf'     && <EPFESICTab />}
      {tab === 'hours'   && <WorkingHoursTab />}
      {tab === 'dpdp'    && <DPDPTab />}
      {tab === 'wages'   && <WagesTab />}
      {tab === 'pt'      && <ProfTaxTab />}
      {tab === 'audit'   && <AuditLogTab />}
    </div>
  )
}
