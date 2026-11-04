/**
 * QR Code Manager — Auth-protected recruiter page
 * Route: /qr-codes
 */

import { apiClient } from '@/lib/api'
import { useEffect,useState } from 'react'
import { AppLayout } from '../components/AppLayout'

interface QRCode {
  id: string
  type: string
  short_code: string
  redirect_url: string
  scan_count: number
  application_count: number
  is_active: boolean
  created_at: string
  job_roles?: { title: string } | null
  hiring_campaigns?: { name: string } | null
}

interface JobRole {
  id: string
  title: string
}

const TYPE_COLORS: Record<string, string> = {
  JOB_APPLY: 'bg-purple-100 text-purple-700',
  REFERRAL: 'bg-blue-100 text-blue-700',
  CAMPAIGN: 'bg-green-100 text-green-700',
}

export default function QRCodeManager() {
  const [qrCodes, setQrCodes] = useState<QRCode[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [showQRModal, setShowQRModal] = useState<{ image: string; url: string; code: string } | null>(null)
  const [jobRoles, setJobRoles] = useState<JobRole[]>([])

  // Form state
  const [formType, setFormType] = useState('JOB_APPLY')
  const [formJobRoleId, setFormJobRoleId] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generated, setGenerated] = useState<{
    qr_code_id: string
    short_code: string
    qr_image_base64: string
    redirect_url: string
  } | null>(null)

  const fetchQRCodes = async () => {
    try {
      const resp = await apiClient.get('/mobile/qr-codes')
      setQrCodes(resp.data.qr_codes || [])
    } catch {
      setError('Failed to load QR codes.')
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

  useEffect(() => {
    fetchQRCodes()
    fetchJobRoles()
  }, [])

  const handleGenerate = async () => {
    setGenerating(true)
    setGenerated(null)
    try {
      const resp = await apiClient.post('/mobile/qr-codes/generate', {
        type: formType,
        job_role_id: formJobRoleId || null,
      })
      setGenerated(resp.data)
      fetchQRCodes()
    } catch {
      setError('Failed to generate QR code.')
    } finally {
      setGenerating(false)
    }
  }

  const handleDeactivate = async (id: string) => {
    try {
      await apiClient.post(`/mobile/qr-codes/${id}/deactivate`)
      setQrCodes((prev) =>
        prev.map((qr) => (qr.id === id ? { ...qr, is_active: false } : qr))
      )
    } catch {
      setError('Failed to deactivate QR code.')
    }
  }

  const downloadQR = (base64: string, code: string) => {
    const link = document.createElement('a')
    link.href = base64
    link.download = `qr-${code}.png`
    link.click()
  }

  const conversionRate = (qr: QRCode) => {
    if (!qr.scan_count) return '0%'
    return `${Math.round((qr.application_count / qr.scan_count) * 100)}%`
  }

  return (
    <AppLayout>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">QR Code Manager</h1>
            <p className="text-gray-500 text-sm mt-0.5">Generate and track QR codes for job applications</p>
          </div>
          <button
            onClick={() => { setShowModal(true); setGenerated(null) }}
            className="flex items-center gap-2 bg-purple-600 text-white px-4 py-2.5 rounded-xl font-medium hover:bg-purple-700 transition shadow-sm"
          >
            + Generate QR Code
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">Total QR Codes</p>
            <p className="text-2xl font-bold text-gray-900">{qrCodes.length}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">Total Scans</p>
            <p className="text-2xl font-bold text-purple-700">
              {qrCodes.reduce((s, q) => s + q.scan_count, 0)}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">Applications via QR</p>
            <p className="text-2xl font-bold text-green-700">
              {qrCodes.reduce((s, q) => s + q.application_count, 0)}
            </p>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center">
              <div className="w-8 h-8 border-4 border-purple-400 border-t-transparent rounded-full animate-spin mx-auto" />
            </div>
          ) : qrCodes.length === 0 ? (
            <div className="p-12 text-center text-gray-400">
              <div className="text-4xl mb-3">📱</div>
              <p className="font-medium">No QR codes yet</p>
              <p className="text-sm">Generate your first QR code to get started.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Code</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Role / Campaign</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Scans</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Apps</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Conv.</th>
                    <th className="text-center px-4 py-3 font-medium text-gray-600">Status</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {qrCodes.map((qr) => (
                    <tr key={qr.id} className="hover:bg-gray-50 transition">
                      <td className="px-4 py-3 font-mono text-purple-700 font-medium">
                        {qr.short_code}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TYPE_COLORS[qr.type] || 'bg-gray-100 text-gray-600'}`}>
                          {qr.type.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {qr.job_roles?.title || qr.hiring_campaigns?.name || '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-medium">{qr.scan_count}</td>
                      <td className="px-4 py-3 text-right font-medium">{qr.application_count}</td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-medium ${qr.application_count > 0 ? 'text-green-600' : 'text-gray-400'}`}>
                          {conversionRate(qr)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${qr.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                          {qr.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setShowQRModal({
                              image: '',
                              url: qr.redirect_url,
                              code: qr.short_code,
                            })}
                            className="text-xs px-2 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 transition text-gray-600"
                          >
                            View
                          </button>
                          {qr.is_active && (
                            <button
                              onClick={() => handleDeactivate(qr.id)}
                              className="text-xs px-2 py-1 rounded-lg bg-red-50 hover:bg-red-100 transition text-red-600"
                            >
                              Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Generate QR Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 px-4">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold">Generate QR Code</h3>
              <button onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>

            {!generated ? (
              <>
                {/* Type */}
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Type</label>
                  <select
                    value={formType}
                    onChange={(e) => setFormType(e.target.value)}
                    className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm"
                  >
                    <option value="JOB_APPLY">Job Apply</option>
                    <option value="REFERRAL">Referral</option>
                    <option value="CAMPAIGN">Campaign</option>
                  </select>
                </div>

                {/* Job role (for JOB_APPLY) */}
                {formType === 'JOB_APPLY' && (
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Job Role</label>
                    <select
                      value={formJobRoleId}
                      onChange={(e) => setFormJobRoleId(e.target.value)}
                      className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm"
                    >
                      <option value="">Select job role...</option>
                      {jobRoles.map((jr) => (
                        <option key={jr.id} value={jr.id}>{jr.title}</option>
                      ))}
                    </select>
                  </div>
                )}

                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="w-full bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 transition disabled:opacity-50"
                >
                  {generating ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Generating...
                    </span>
                  ) : 'Generate'}
                </button>
              </>
            ) : (
              <>
                <div className="text-center mb-4">
                  <div className="text-3xl mb-2">✅</div>
                  <p className="font-bold text-gray-900">QR Code Generated!</p>
                  <p className="text-sm text-gray-500 font-mono mt-1">{generated.short_code}</p>
                </div>

                {generated.qr_image_base64 && (
                  <div className="flex justify-center mb-4">
                    <img
                      src={generated.qr_image_base64}
                      alt="QR Code"
                      className="w-48 h-48 border border-gray-200 rounded-xl"
                    />
                  </div>
                )}

                <p className="text-xs text-gray-400 break-all text-center mb-4">{generated.redirect_url}</p>

                <div className="space-y-2">
                  <button
                    onClick={() => navigator.clipboard.writeText(generated.redirect_url)}
                    className="w-full py-2.5 rounded-xl border border-gray-300 text-sm font-medium hover:bg-gray-50 transition"
                  >
                    Copy Link
                  </button>
                  {generated.qr_image_base64 && (
                    <button
                      onClick={() => downloadQR(generated.qr_image_base64, generated.short_code)}
                      className="w-full py-2.5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-800 transition"
                    >
                      Download PNG
                    </button>
                  )}
                  <button
                    onClick={() => setShowModal(false)}
                    className="w-full py-2.5 text-sm text-gray-500 hover:text-gray-700"
                  >
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* View QR Modal */}
      {showQRModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 px-4">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl text-center">
            <h3 className="text-lg font-bold mb-2">QR Code</h3>
            <p className="text-sm font-mono text-purple-600 mb-4">{showQRModal.code}</p>
            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <p className="text-xs text-gray-400 break-all">{showQRModal.url}</p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => navigator.clipboard.writeText(showQRModal.url)}
                className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium hover:bg-gray-50 transition"
              >
                Copy Link
              </button>
              <button
                onClick={() => setShowQRModal(null)}
                className="flex-1 py-2.5 rounded-xl bg-gray-900 text-white text-sm font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
