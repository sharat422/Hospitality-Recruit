/**
 * Video Reviewer — Recruiter-facing video review page (AUTH required)
 * Route: /video-review/:interviewId
 */

import { apiClient } from '@/lib/api'
import { useEffect,useRef,useState } from 'react'
import { useNavigate,useParams } from 'react-router-dom'
import { AppLayout } from '../components/AppLayout'

interface Question {
  id: string
  question_text: string
  time_limit_seconds: number
  order_index: number
}

interface Candidate {
  full_name: string
  email: string
  phone: string
}

interface JobRole {
  title: string
}

interface Interview {
  id: string
  interview_type: string
  recording_url: string | null
  duration_seconds: number
  status: string
  recruiter_rating: number | null
  recruiter_notes: string | null
  questions: Question[]
  candidates: Candidate | null
  job_roles: JobRole | null
}

export default function VideoReviewer() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()

  const [interview, setInterview] = useState<Interview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [currentQuestionIdx, setCurrentQuestionIdx] = useState(0)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [rating, setRating] = useState(0)
  const [hoveredStar, setHoveredStar] = useState(0)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [showShareModal, setShowShareModal] = useState(false)
  const [shareEmail, setShareEmail] = useState('')

  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    if (!interviewId || interviewId === 'new') {
      setLoading(false)
      return
    }
    const fetchInterview = async () => {
      try {
        const resp = await apiClient.get(`/mobile/video-interviews/${interviewId}/review`)
        const data = resp.data
        setInterview(data)
        setRating(data.recruiter_rating || 0)
        setNotes(data.recruiter_notes || '')
      } catch {
        setError('Failed to load interview.')
      } finally {
        setLoading(false)
      }
    }
    fetchInterview()
  }, [interviewId])

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = playbackSpeed
    if (audioRef.current) audioRef.current.playbackRate = playbackSpeed
  }, [playbackSpeed])

  const handleSaveReview = async () => {
    if (!interview || !interviewId) return
    setSaving(true)
    try {
      await apiClient.patch(`/mobile/video-interviews/${interviewId}/rate`, {
        rating,
        notes,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      setInterview((prev) => prev ? { ...prev, recruiter_rating: rating, recruiter_notes: notes, status: 'REVIEWED' } : prev)
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  const handleShare = () => {
    alert(`Share feature: would email ${shareEmail || 'manager'} with a link to this review.`)
    setShowShareModal(false)
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <div className="w-10 h-10 border-4 border-purple-400 border-t-transparent rounded-full animate-spin" />
        </div>
      </AppLayout>
    )
  }

  if (!interviewId || interviewId === 'new') {
    return (
      <AppLayout>
        <div className="max-w-2xl mx-auto py-12 text-center">
          <div className="text-5xl mb-4">🎬</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Video Reviewer</h1>
          <p className="text-gray-500 mb-6">Enter a video interview ID to review.</p>
          <input
            type="text"
            placeholder="Interview ID (UUID)"
            className="border border-gray-300 rounded-xl px-4 py-3 w-full max-w-sm mx-auto block mb-4"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const val = (e.target as HTMLInputElement).value.trim()
                if (val) navigate(`/video-review/${val}`)
              }
            }}
          />
          <p className="text-xs text-gray-400">Press Enter to load interview</p>
        </div>
      </AppLayout>
    )
  }

  if (error || !interview) {
    return (
      <AppLayout>
        <div className="text-center py-12">
          <p className="text-red-500">{error || 'Interview not found.'}</p>
        </div>
      </AppLayout>
    )
  }

  const questions: Question[] = Array.isArray(interview.questions) ? interview.questions : []
  const currentQuestion = questions[currentQuestionIdx]
  const isAudio = interview.interview_type === 'AUDIO' || !interview.recording_url?.includes('.webm')

  return (
    <AppLayout>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Video Interview Review</h1>
            <p className="text-gray-500 text-sm mt-0.5">
              {interview.candidates?.full_name || 'Candidate'} — {interview.job_roles?.title || 'Position'}
            </p>
          </div>
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              interview.status === 'REVIEWED'
                ? 'bg-green-100 text-green-700'
                : interview.status === 'RECORDED'
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-600'
            }`}
          >
            {interview.status}
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left panel — Video + controls */}
          <div className="lg:col-span-2 space-y-4">
            {/* Current question */}
            {currentQuestion && (
              <div className="bg-purple-50 border border-purple-200 rounded-xl px-4 py-3">
                <p className="text-xs font-medium text-purple-500 uppercase tracking-wide mb-1">
                  Question {currentQuestionIdx + 1}
                </p>
                <p className="text-gray-800 font-medium">{currentQuestion.question_text}</p>
              </div>
            )}

            {/* Video/Audio player */}
            <div className="bg-gray-900 rounded-2xl overflow-hidden">
              {interview.recording_url ? (
                isAudio ? (
                  <div className="p-8 text-center">
                    <div className="text-5xl mb-4">🎙️</div>
                    <p className="text-white text-sm mb-4">Audio Recording</p>
                    <audio
                      ref={audioRef}
                      controls
                      src={interview.recording_url}
                      className="w-full"
                    />
                  </div>
                ) : (
                  <video
                    ref={videoRef}
                    controls
                    src={interview.recording_url}
                    className="w-full aspect-video"
                    playsInline
                  />
                )
              ) : (
                <div className="aspect-video flex items-center justify-center">
                  <div className="text-center text-gray-500">
                    <div className="text-4xl mb-2">⏳</div>
                    <p className="text-sm">No recording yet</p>
                  </div>
                </div>
              )}
            </div>

            {/* Speed controls */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 mr-1">Speed:</span>
              {[0.75, 1, 1.25, 1.5].map((speed) => (
                <button
                  key={speed}
                  onClick={() => setPlaybackSpeed(speed)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition ${
                    playbackSpeed === speed
                      ? 'bg-purple-600 text-white border-purple-600'
                      : 'border-gray-300 text-gray-600 hover:border-gray-400'
                  }`}
                >
                  {speed}x
                </button>
              ))}
              {interview.duration_seconds > 0 && (
                <span className="ml-auto text-xs text-gray-400">
                  Duration: {Math.floor(interview.duration_seconds / 60)}m {interview.duration_seconds % 60}s
                </span>
              )}
            </div>

            {/* Question navigation */}
            {questions.length > 1 && (
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setCurrentQuestionIdx((i) => Math.max(0, i - 1))}
                  disabled={currentQuestionIdx === 0}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-lg text-sm font-medium disabled:opacity-40 hover:bg-gray-200 transition"
                >
                  ← Previous
                </button>
                <div className="flex gap-1.5">
                  {questions.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setCurrentQuestionIdx(i)}
                      className={`w-2.5 h-2.5 rounded-full transition ${
                        i === currentQuestionIdx ? 'bg-purple-500' : 'bg-gray-300 hover:bg-gray-400'
                      }`}
                    />
                  ))}
                </div>
                <button
                  onClick={() => setCurrentQuestionIdx((i) => Math.min(questions.length - 1, i + 1))}
                  disabled={currentQuestionIdx === questions.length - 1}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-lg text-sm font-medium disabled:opacity-40 hover:bg-gray-200 transition"
                >
                  Next →
                </button>
              </div>
            )}

            {/* Keyboard hints */}
            <div className="flex flex-wrap gap-3 text-xs text-gray-400">
              <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 bg-gray-100 rounded border border-gray-300 font-mono">Space</kbd> Play/Pause</span>
              <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 bg-gray-100 rounded border border-gray-300 font-mono">←/→</kbd> Seek 5s</span>
              <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 bg-gray-100 rounded border border-gray-300 font-mono">M</kbd> Mute</span>
            </div>
          </div>

          {/* Right panel — Candidate info + review */}
          <div className="space-y-4">
            {/* Candidate card */}
            <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Candidate</h3>
              <p className="text-lg font-bold text-gray-900 mb-1">
                {interview.candidates?.full_name || 'Unknown'}
              </p>
              <p className="text-sm text-gray-500 mb-0.5">{interview.candidates?.email}</p>
              <p className="text-sm text-gray-500">{interview.candidates?.phone}</p>
              {interview.job_roles && (
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-xs text-gray-400">Applying for</p>
                  <p className="text-sm font-medium text-gray-700">{interview.job_roles.title}</p>
                </div>
              )}
            </div>

            {/* Star Rating */}
            <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Rating</h3>
              <div className="flex gap-1 mb-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    onClick={() => setRating(star)}
                    onMouseEnter={() => setHoveredStar(star)}
                    onMouseLeave={() => setHoveredStar(0)}
                    className="text-3xl transition-transform hover:scale-110"
                  >
                    {star <= (hoveredStar || rating) ? '⭐' : '☆'}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-400">
                {rating === 0 ? 'Not rated yet' : `${rating}/5 stars`}
              </p>
            </div>

            {/* Notes */}
            <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Notes</h3>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={5}
                placeholder="Add your notes about this candidate..."
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 resize-none"
              />
            </div>

            {/* Actions */}
            <button
              onClick={handleSaveReview}
              disabled={saving || rating === 0}
              className="w-full bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 transition disabled:opacity-50"
            >
              {saving ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Saving...
                </span>
              ) : saved ? (
                '✓ Saved!'
              ) : (
                'Save Review'
              )}
            </button>

            <button
              onClick={() => setShowShareModal(true)}
              className="w-full bg-gray-100 text-gray-700 py-3 rounded-xl font-medium hover:bg-gray-200 transition"
            >
              Share with Manager
            </button>
          </div>
        </div>
      </div>

      {/* Share Modal */}
      {showShareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 px-4">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-lg font-bold mb-4">Share with Manager</h3>
            <input
              type="email"
              placeholder="Manager's email address"
              value={shareEmail}
              onChange={(e) => setShareEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-purple-400"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowShareModal(false)}
                className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleShare}
                className="flex-1 py-2.5 rounded-xl bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 transition"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
