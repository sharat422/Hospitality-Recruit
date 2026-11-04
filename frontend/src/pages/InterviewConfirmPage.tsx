import axios from 'axios'
import React,{ useEffect,useState } from 'react'
import { useParams } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

interface SlotDetails {
  id: string
  start_time: string
  end_time: string
  status: string
  job_role?: { title?: string; location?: string; description?: string }
  candidate?: { name?: string; full_name?: string; email?: string }
  recruiter?: { full_name?: string; email?: string; phone?: string }
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
}

type ActionState = 'idle' | 'confirmed' | 'rescheduled' | 'loading'

export const InterviewConfirmPage: React.FC = () => {
  const { token } = useParams<{ token: string }>()
  const [slot, setSlot] = useState<SlotDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [actionState, setActionState] = useState<ActionState>('idle')

  useEffect(() => {
    if (!token) { setError(true); setLoading(false); return }
    axios.get(`${API_BASE}/engagement/interviews/confirm/${token}`)
      .then(res => { setSlot(res.data); setLoading(false) })
      .catch(() => { setError(true); setLoading(false) })
  }, [token])

  const handleAction = async (action: 'confirm' | 'reschedule') => {
    if (!token) return
    setActionState('loading')
    try {
      await axios.post(`${API_BASE}/engagement/interviews/confirm/${token}`, { action })
      setActionState(action === 'confirm' ? 'confirmed' : 'rescheduled')
    } catch {
      alert('Something went wrong. Please try again.')
      setActionState('idle')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-purple-600 border-t-transparent rounded-full"></div>
      </div>
    )
  }

  if (error || !slot) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="text-center max-w-sm">
          <div className="text-5xl mb-4">😕</div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Interview not found</h1>
          <p className="text-gray-500">This link may be invalid or expired.</p>
        </div>
      </div>
    )
  }

  const roleName = slot.job_role?.title || 'Interview'
  const location = slot.job_role?.location
  const isInPerson = location && !location.toLowerCase().includes('zoom') && !location.toLowerCase().includes('video') && !location.toLowerCase().includes('remote')
  const recruiter = slot.recruiter
  const mapsUrl = location ? `https://www.google.com/maps/search/${encodeURIComponent(location)}` : null

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-blue-50 flex items-start justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-8 h-8 bg-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white text-xs font-bold">HR</span>
            </div>
            <span className="text-xl font-bold text-purple-600">HospRecruit</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">{roleName}</h1>
          {slot.candidate && (
            <p className="text-gray-500 text-sm mt-1">
              Hi {slot.candidate.name || slot.candidate.full_name || 'there'}!
            </p>
          )}
        </div>

        {/* Interview details card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-4">
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl">📅</span>
              <div>
                <div className="font-semibold text-gray-900">{formatDate(slot.start_time)}</div>
                <div className="text-gray-500 text-sm">{formatTime(slot.start_time)} – {formatTime(slot.end_time)}</div>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <span className="text-2xl">{isInPerson ? '📍' : '💻'}</span>
              <div>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full ${
                  isInPerson ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'
                }`}>
                  {isInPerson ? 'In Person 📍' : 'Video 💻'}
                </span>
                {location && (
                  <div className="text-gray-500 text-sm mt-1">
                    {mapsUrl && isInPerson ? (
                      <a href={mapsUrl} target="_blank" rel="noopener noreferrer" className="text-purple-600 hover:underline">
                        {location}
                      </a>
                    ) : (
                      <span>{location}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-4">
          {actionState === 'confirmed' ? (
            <div className="text-center py-4">
              <div className="text-4xl mb-3">✅</div>
              <div className="font-bold text-green-700 text-lg">Confirmed! See you then!</div>
              <p className="text-gray-500 text-sm mt-2">We'll send you a reminder closer to the time.</p>
            </div>
          ) : actionState === 'rescheduled' ? (
            <div className="text-center py-4">
              <div className="text-4xl mb-3">📅</div>
              <div className="font-bold text-blue-700 text-lg">Got it!</div>
              <p className="text-gray-500 text-sm mt-2">We'll be in touch to find a new time that works for you.</p>
            </div>
          ) : (
            <>
              <p className="text-sm text-gray-600 text-center mb-4">
                Please confirm your attendance for this interview.
              </p>
              <button
                onClick={() => handleAction('confirm')}
                disabled={actionState === 'loading'}
                className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3.5 rounded-xl text-base transition disabled:opacity-50 mb-3"
              >
                {actionState === 'loading' ? 'Processing...' : 'Confirm Interview ✓'}
              </button>
              <button
                onClick={() => handleAction('reschedule')}
                disabled={actionState === 'loading'}
                className="w-full text-center text-sm text-gray-500 hover:text-gray-700 py-2 transition disabled:opacity-50"
              >
                Request a different time →
              </button>
            </>
          )}
        </div>

        {/* Recruiter footer */}
        {recruiter && (
          <div className="text-center text-sm text-gray-500">
            <p className="font-medium text-gray-700">{recruiter.full_name || 'Your Recruiter'}</p>
            {recruiter.phone && (
              <a href={`tel:${recruiter.phone}`} className="text-purple-600 hover:underline">{recruiter.phone}</a>
            )}
            {recruiter.email && !recruiter.phone && (
              <a href={`mailto:${recruiter.email}`} className="text-purple-600 hover:underline">{recruiter.email}</a>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default InterviewConfirmPage
