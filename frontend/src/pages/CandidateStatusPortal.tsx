import axios from 'axios'
import React,{ useEffect,useState } from 'react'
import { useParams } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

const STAGES = [
  ['APPLIED', 'Applied', 'आवेदन'],
  ['SCREENED', 'Screened', 'जाँच पूरी'],
  ['SHORTLISTED', 'Shortlisted', 'चयनित सूची'],
  ['INTERVIEW', 'Interview', 'साक्षात्कार'],
  ['SELECTED', 'Selected', 'चयनित'],
  ['OFFER', 'Offer', 'ऑफर'],
  ['OFFER_ACCEPTED', 'Offer accepted', 'ऑफर स्वीकार'],
  ['ONBOARDING', 'Onboarding', 'जॉइनिंग प्रक्रिया'],
  ['HIRED', 'Hired', 'नियुक्त'],
] as const

const STAGE_ALIASES: Record<string, string> = {
  REVIEWING: 'SCREENED', INTERVIEW_SCHEDULED: 'INTERVIEW', OFFER_SENT: 'OFFER', OFFERED: 'OFFER',
}

interface PortalData {
  name?: string
  email?: string
  pipeline_stage?: string
  job_role?: { title?: string; location?: string }
  interview_slots?: Array<{
    start_time: string
    end_time: string
    status: string
  }>
  recruiter?: { full_name?: string; email?: string; phone?: string }
  recruiter_phone?: string
}

function formatDateTime(iso: string): { date: string; time: string } {
  const d = new Date(iso)
  return {
    date: d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }),
    time: d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }),
  }
}

export const CandidateStatusPortal: React.FC = () => {
  const { token } = useParams<{ token: string }>()
  const [data, setData] = useState<PortalData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [language, setLanguage] = useState<'hi' | 'en'>('hi')

  useEffect(() => {
    if (!token) { setError(true); setLoading(false); return }
    axios.get(`${API_BASE}/engagement/portal/${token}`)
      .then(res => { setData(res.data); setLoading(false) })
      .catch(() => { setError(true); setLoading(false) })
  }, [token])

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-purple-600 border-t-transparent rounded-full"></div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="text-center max-w-sm">
          <div className="text-5xl mb-4">😕</div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Application not found</h1>
          <p className="text-gray-500">The link may be invalid or expired.</p>
        </div>
      </div>
    )
  }

  const rawStage = String(data.pipeline_stage || 'APPLIED').toUpperCase()
  const normalizedStage = STAGE_ALIASES[rawStage] || rawStage
  const currentStageIdx = Math.max(0, STAGES.findIndex(stage => stage[0] === normalizedStage))
  const recruiterPhone = data.recruiter_phone || data.recruiter?.phone
  const upcomingSlot = (data.interview_slots || []).find(s => s.status === 'BOOKED' || s.status === 'INVITED')

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-blue-50 px-4 py-8 flex items-start justify-center">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="flex justify-end mb-2"><button onClick={() => setLanguage(v => v === 'hi' ? 'en' : 'hi')} className="min-h-11 px-3 rounded-lg border border-gray-200 bg-white text-sm font-semibold">{language === 'hi' ? 'English' : 'हिंदी'}</button></div>
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white text-xs font-bold">HR</span>
            </div>
            <span className="text-xl font-bold text-purple-600">HospRecruit</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">
            {data.job_role?.title || 'Your Application'}
          </h1>
          {data.job_role?.location && (
            <p className="text-gray-500 mt-1">{data.job_role.location}</p>
          )}
        </div>

        {/* Status Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-4">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
              <span className="text-purple-700 font-bold text-sm">
                {(data.name || '?')[0]?.toUpperCase()}
              </span>
            </div>
            <div>
              <div className="font-semibold text-gray-900">{data.name || 'Candidate'}</div>
              <div className="text-xs text-gray-500">{data.email}</div>
            </div>
          </div>

          {/* Progress stepper */}
          <div className="space-y-3">
            {STAGES.map((stage, idx) => {
              const isDone = idx < currentStageIdx
              const isCurrent = idx === currentStageIdx
              const label = language === 'hi' ? stage[2] : stage[1]
              return (
                <div key={stage[0]} className="flex items-center gap-3 min-h-11">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold border-2 ${
                    isDone
                      ? 'bg-green-500 border-green-500 text-white'
                      : isCurrent
                        ? 'bg-purple-600 border-purple-600 text-white'
                        : 'bg-white border-gray-200 text-gray-300'
                  }`}>
                    {isDone ? '✓' : idx + 1}
                  </div>
                  <div className="flex-1">
                    <span className={`text-sm font-medium ${
                      isDone ? 'text-green-700' : isCurrent ? 'text-purple-700' : 'text-gray-400'
                    }`}>
                      {label}
                    </span>
                    {isCurrent && (
                      <span className="ml-2 text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">Current</span>
                    )}
                  </div>
                  {idx < STAGES.length - 1 && (
                    <div className={`w-px h-3 absolute`} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Interview card */}
        {upcomingSlot && (
          <div className="bg-white rounded-2xl shadow-sm border border-purple-100 p-6 mb-4">
            <h3 className="font-semibold text-gray-900 mb-3">Interview Details</h3>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-gray-700">
                <span>📅</span>
                <span>{formatDateTime(upcomingSlot.start_time).date}</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-700">
                <span>⏰</span>
                <span>{formatDateTime(upcomingSlot.start_time).time} – {formatDateTime(upcomingSlot.end_time).time}</span>
              </div>
              <div className="inline-flex items-center gap-1 mt-1">
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                  upcomingSlot.status === 'BOOKED' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                }`}>
                  {upcomingSlot.status === 'BOOKED' ? '✓ Confirmed' : 'Pending confirmation'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Recruiter contact */}
        {recruiterPhone && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <p className="text-sm text-gray-600 mb-3">
              Have questions? Your recruiter is here to help.
            </p>
            <a
              href={`sms:${recruiterPhone}`}
              className="flex items-center justify-center gap-2 w-full bg-purple-600 hover:bg-purple-700 text-white rounded-xl py-3 font-medium transition text-sm"
            >
              <span>💬</span>
              Text Us
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

export default CandidateStatusPortal
