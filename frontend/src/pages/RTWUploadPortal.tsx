import { apiClient } from '@/lib/api'
import { CheckCircle,FileText,Upload } from 'lucide-react'
import { useEffect,useState } from 'react'
import { useParams } from 'react-router-dom'

const DOCUMENT_TYPES = [
  { value: 'PASSPORT', label: 'Passport' },
  { value: 'BRP_CARD', label: 'BRP Card' },
  { value: 'NATIONAL_ID', label: 'National ID Card' },
  { value: 'SHARE_CODE', label: 'Share Code' },
  { value: 'J1_VISA', label: 'J-1 Visa Stamp' },
  { value: 'H2B_APPROVAL', label: 'H-2B Approval Notice' },
  { value: 'DRIVERS_LICENSE', label: "Driver's License" },
  { value: 'SSN_CARD', label: 'SSN Card' },
]

interface UploadInfo {
  check_type?: string
  candidate_id?: string
  [key: string]: unknown
}

interface ExtractedFields {
  document_type?: string
  name?: string
  nationality?: string
  expiry_date?: string
  [key: string]: unknown
}

export default function RTWUploadPortal() {
  const { token } = useParams<{ token: string }>()

  const [info, setInfo] = useState<UploadInfo | null>(null)
  const [infoLoading, setInfoLoading] = useState(true)
  const [infoError, setInfoError] = useState(false)

  const [docType, setDocType] = useState('PASSPORT')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [extractedFields, setExtractedFields] = useState<ExtractedFields | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (!token) return
    const fetch = async () => {
      setInfoLoading(true)
      try {
        const res = await apiClient.get(`/compliance/rtw/upload-info/${token}`)
        setInfo(res.data)
      } catch {
        setInfoError(true)
      } finally {
        setInfoLoading(false)
      }
    }
    fetch()
  }, [token])

  const handleUpload = async () => {
    if (!file || !token) return
    setUploading(true)
    setUploadError('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('document_type', docType)
      const res = await apiClient.post(`/compliance/rtw/upload/${token}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setExtractedFields(res.data?.extracted_fields || null)
      setSuccess(true)
    } catch {
      setUploadError('Upload failed. Please try again.')
    } finally {
      setUploading(false)
    }
  }

  if (infoLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-400 text-sm">Loading...</div>
      </div>
    )
  }

  if (infoError || !info) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white rounded-2xl shadow-lg p-8 text-center">
          <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
            <FileText className="w-7 h-7 text-red-400" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Invalid Upload Link</h2>
          <p className="text-sm text-gray-500">This upload link is invalid or has expired.</p>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white rounded-2xl shadow-lg py-10 px-6 text-center">
          <div className="w-16 h-16 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-9 h-9 text-green-500" />
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Documents Submitted</h2>
          <p className="text-sm text-gray-500 mb-6">
            Documents submitted successfully! Your recruiter will review within 24 hours.
          </p>

          {extractedFields && (
            <div className="text-left bg-gray-50 rounded-xl p-4 space-y-2">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Extracted Information</h3>
              {extractedFields.document_type && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Document Type</span>
                  <span className="text-gray-800 font-medium">{extractedFields.document_type}</span>
                </div>
              )}
              {extractedFields.name && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Name</span>
                  <span className="text-gray-800 font-medium">{extractedFields.name}</span>
                </div>
              )}
              {extractedFields.nationality && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Nationality</span>
                  <span className="text-gray-800 font-medium">{extractedFields.nationality}</span>
                </div>
              )}
              {extractedFields.expiry_date && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Expiry Date</span>
                  <span className="text-gray-800 font-medium">
                    {new Date(extractedFields.expiry_date).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-lg py-8 px-6 space-y-6">
        {/* Header */}
        <div className="text-center">
          <p className="text-2xl font-bold text-purple-600 mb-1">HospRecruit</p>
          <h1 className="text-lg font-semibold text-gray-900">Right to Work Documents</h1>
          <p className="text-sm text-gray-500 mt-1">Please upload your right to work documentation</p>
        </div>

        {/* Check info card */}
        <div className="bg-purple-50 rounded-xl p-4 border border-purple-100">
          <p className="text-xs text-purple-600 font-medium uppercase tracking-wide mb-1">Check Type</p>
          <p className="text-sm font-semibold text-purple-900">{info.check_type ?? 'RTW Check'}</p>
        </div>

        {/* Document type selector */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Document Type</label>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {DOCUMENT_TYPES.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
        </div>

        {/* File input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Upload Document</label>
          <label className="block cursor-pointer">
            <div className={`border-2 border-dashed rounded-xl p-6 text-center transition ${
              file ? 'border-purple-300 bg-purple-50' : 'border-gray-300 hover:border-purple-300 hover:bg-gray-50'
            }`}>
              <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? 'text-purple-500' : 'text-gray-400'}`} />
              {file ? (
                <div>
                  <p className="text-sm font-medium text-purple-700">{file.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-gray-500">Click to select a file</p>
                  <p className="text-xs text-gray-400 mt-0.5">Images or PDF accepted</p>
                </div>
              )}
            </div>
            <input
              type="file"
              accept="image/*,application/pdf"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        {uploadError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
            {uploadError}
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="w-full py-3 bg-purple-600 text-white rounded-xl font-medium text-sm hover:bg-purple-700 disabled:opacity-50 transition"
        >
          {uploading ? 'Uploading...' : 'Upload Document'}
        </button>
      </div>
    </div>
  )
}
