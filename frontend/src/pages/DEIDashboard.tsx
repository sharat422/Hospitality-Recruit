import { apiClient } from '@/lib/api'
import { Check,Equal,Info } from 'lucide-react'
import React,{ useEffect,useState } from 'react'
import {
Bar,
BarChart,
CartesianGrid,
ResponsiveContainer,
Tooltip,
XAxis,YAxis,
} from 'recharts'

// --- Types ---
interface EEOReport {
  total: number
  by_gender?: Record<string, number>
  by_ethnicity?: Record<string, number>
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500)
    return () => clearTimeout(t)
  }, [onClose])
  return (
    <div className="fixed bottom-6 right-6 z-50 bg-purple-700 text-white px-5 py-3 rounded-xl shadow-lg text-sm flex items-center gap-3">
      <Check className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

// ============ EEO ANALYTICS TAB ============
function EEOAnalyticsTab() {
  const [report, setReport] = useState<EEOReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const res = await apiClient.get('/compliance/eeo/report')
        setReport(res.data)
      } catch {
        console.error('Failed to fetch EEO report')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [])

  const handleExport = async () => {
    setExporting(true)
    try {
      const currentYear = new Date().getFullYear()
      const res = await apiClient.post(
        '/compliance/eeo/report/export',
        { year: currentYear, format: 'csv' },
        { responseType: 'blob' }
      )
      const blob = new Blob([res.data], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'eeo_report.csv'
      a.click()
      URL.revokeObjectURL(url)
      setToast('EEO report exported')
    } catch {
      setToast('Export failed')
    } finally {
      setExporting(false)
    }
  }

  const genderData = report?.by_gender
    ? Object.entries(report.by_gender).map(([key, value]) => ({ name: key.replace(/_/g, ' '), value }))
    : []

  const ethnicityData = report?.by_ethnicity
    ? Object.entries(report.by_ethnicity).map(([key, value]) => ({ name: key.replace(/_/g, ' '), value }))
    : []

  if (loading) return <div className="py-12 text-center text-gray-400">Loading EEO data...</div>

  return (
    <div className="space-y-6">
      {/* Total + Export */}
      <div className="flex items-center justify-between">
        <div className="bg-white rounded-xl border border-gray-200 px-6 py-4">
          <p className="text-sm text-gray-500">Total Applications</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{report?.total ?? 0}</p>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition"
        >
          {exporting ? 'Exporting...' : 'Export CSV'}
        </button>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-900 mb-4">Applications by Gender</h3>
          {genderData.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No data</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={genderData} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#7c3aed" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-900 mb-4">Applications by Ethnicity</h3>
          {ethnicityData.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No data</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={ethnicityData} margin={{ top: 0, right: 0, left: -20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#7c3aed" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ COLLECT DATA TAB ============
function CollectDataTab() {
  const [candidateId, setCandidateId] = useState('')
  const [gender, setGender] = useState('')
  const [ethnicity, setEthnicity] = useState('')
  const [disabilityStatus, setDisabilityStatus] = useState('')
  const [veteranStatus, setVeteranStatus] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!candidateId.trim()) return
    setSubmitting(true)
    try {
      const body: Record<string, string> = { candidate_id: candidateId }
      if (gender) body.gender = gender
      if (ethnicity) body.ethnicity = ethnicity
      if (disabilityStatus) body.disability_status = disabilityStatus
      if (veteranStatus) body.veteran_status = veteranStatus
      await apiClient.post('/compliance/eeo/collect', body)
      setToast('EEO data collected successfully')
      setCandidateId('')
      setGender('')
      setEthnicity('')
      setDisabilityStatus('')
      setVeteranStatus('')
    } catch {
      setToast('Failed to collect EEO data')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Info banner */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
        <p className="text-sm text-blue-700">
          This data is collected anonymously and never shown alongside candidate profiles.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-5">Collect EEO Data</h3>
        <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Candidate ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={candidateId}
              onChange={(e) => setCandidateId(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="e.g. cand_abc123"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Gender (optional)</label>
            <select
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="">Select...</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
              <option value="NON_BINARY">Non-binary</option>
              <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Ethnicity (optional)</label>
            <select
              value={ethnicity}
              onChange={(e) => setEthnicity(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="">Select...</option>
              <option value="WHITE">White</option>
              <option value="BLACK">Black</option>
              <option value="ASIAN">Asian</option>
              <option value="HISPANIC">Hispanic</option>
              <option value="MIXED">Mixed</option>
              <option value="OTHER">Other</option>
              <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Disability Status (optional)</label>
            <select
              value={disabilityStatus}
              onChange={(e) => setDisabilityStatus(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="">Select...</option>
              <option value="YES">Yes</option>
              <option value="NO">No</option>
              <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Veteran Status (optional)</label>
            <select
              value={veteranStatus}
              onChange={(e) => setVeteranStatus(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="">Select...</option>
              <option value="YES">Yes</option>
              <option value="NO">No</option>
              <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={submitting || !candidateId.trim()}
            className="px-5 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition"
          >
            {submitting ? 'Submitting...' : 'Submit'}
          </button>
        </form>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ BLIND SCREENING TAB ============
function BlindScreeningTab() {
  const [jobId, setJobId] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!jobId.trim()) return
    setSubmitting(true)
    try {
      await apiClient.patch(`/compliance/jobs/${jobId}/blind-screening`, { enabled })
      setToast(`Blind screening ${enabled ? 'enabled' : 'disabled'} for job ${jobId}`)
    } catch {
      setToast('Failed to update blind screening settings')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Info card */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
            <Equal className="w-5 h-5 text-purple-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">About Blind Screening</h3>
            <p className="text-sm text-gray-600 mt-1">
              When enabled, the recruiter sees "Candidate #XXXX" instead of the candidate's name,
              and location or age indicators are hidden from their view. This reduces unconscious
              bias during early screening stages.
            </p>
          </div>
        </div>
      </div>

      {/* Form */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-5">Configure Blind Screening</h3>
        <form onSubmit={handleSubmit} className="space-y-4 max-w-md">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Job ID</label>
            <input
              type="text"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="e.g. job_abc123"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
            </label>
            <span className="text-sm font-medium text-gray-700">
              {enabled ? 'Blind Screening Enabled' : 'Blind Screening Disabled'}
            </span>
          </div>
          <button
            type="submit"
            disabled={submitting || !jobId.trim()}
            className="px-5 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition"
          >
            {submitting ? 'Saving...' : 'Save Settings'}
          </button>
        </form>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ MAIN PAGE ============
type Tab = 'eeo' | 'collect' | 'blind'

export default function DEIDashboard() {
  const [tab, setTab] = useState<Tab>('eeo')

  const tabs: { key: Tab; label: string }[] = [
    { key: 'eeo', label: 'EEO Analytics' },
    { key: 'collect', label: 'Collect Data' },
    { key: 'blind', label: 'Blind Screening' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Equal className="w-6 h-6 text-purple-600" />
        <h1 className="text-2xl font-bold text-gray-900">DEI Dashboard</h1>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition -mb-px ${
              tab === t.key
                ? 'border-purple-600 text-purple-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'eeo' && <EEOAnalyticsTab />}
      {tab === 'collect' && <CollectDataTab />}
      {tab === 'blind' && <BlindScreeningTab />}
    </div>
  )
}
