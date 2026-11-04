/**
 * Video Recorder — Candidate-facing video interview page (PUBLIC)
 * Route: /video-interview/:token
 */

import axios from 'axios'
import { useEffect,useRef,useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

interface Question {
  id: string
  question_text: string
  time_limit_seconds: number
  order_index: number
}

interface InterviewData {
  interview_id: string
  interview_type: string
  questions: Question[]
  candidate_name: string
  role_name: string
  status: string
}

type Stage = 'welcome' | 'recording' | 'uploading' | 'done' | 'error'

export default function VideoRecorder() {
  const { token } = useParams<{ token: string }>()
  const { t } = useTranslation('candidate')

  const [interview, setInterview] = useState<InterviewData | null>(null)
  const [stage, setStage] = useState<Stage>('welcome')
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [isRecording, setIsRecording] = useState(false)
  const [audioOnly, setAudioOnly] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [timeLeft, setTimeLeft] = useState(0)
  const [cameraError, setCameraError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const videoRef = useRef<HTMLVideoElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const fetchInterview = async () => {
      try {
        const resp = await axios.get(`${API_BASE}/mobile/video-interviews/candidate/${token}`)
        setInterview(resp.data)
      } catch {
        setError('Interview not found or link has expired.')
        setStage('error')
      } finally {
        setLoading(false)
      }
    }
    if (token) fetchInterview()
  }, [token])

  const startStream = async (audioOnlyMode: boolean) => {
    try {
      const constraints = audioOnlyMode
        ? { audio: true, video: false }
        : { audio: true, video: { facingMode: 'user' } }

      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream

      if (!audioOnlyMode && videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.muted = true
        videoRef.current.play()
      }
      return stream
    } catch {
      setCameraError(true)
      // Auto-fallback to audio only
      if (!audioOnlyMode) {
        setAudioOnly(true)
        return startStream(true)
      }
      throw new Error('Media access denied')
    }
  }

  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }

  const startRecording = async () => {
    if (!interview) return
    const q = interview.questions[currentQuestionIndex]
    setTimeLeft(q.time_limit_seconds)
    chunksRef.current = []

    try {
      const stream = await startStream(audioOnly)
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
        ? 'video/webm;codecs=vp9'
        : MediaRecorder.isTypeSupported('video/webm')
        ? 'video/webm'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.start(1000)
      setIsRecording(true)

      // Countdown timer
      timerRef.current = setInterval(() => {
        setTimeLeft((prev) => {
          if (prev <= 1) {
            stopRecording()
            return 0
          }
          return prev - 1
        })
      }, 1000)
    } catch {
      setError('Could not access camera or microphone.')
    }
  }

  const stopRecording = () => {
    if (timerRef.current) clearInterval(timerRef.current)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    stopStream()
    setIsRecording(false)
  }

  const uploadRecording = async () => {
    if (!interview || chunksRef.current.length === 0) return
    setStage('uploading')
    setUploadProgress(0)

    const blob = new Blob(chunksRef.current, { type: 'video/webm' })
    const formData = new FormData()
    formData.append('file', blob, `recording_${currentQuestionIndex + 1}.webm`)

    // Simulate upload progress
    const progressInterval = setInterval(() => {
      setUploadProgress((prev) => Math.min(prev + 10, 90))
    }, 200)

    try {
      await axios.post(`${API_BASE}/mobile/video-interviews/${interview.interview_id}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      clearInterval(progressInterval)
      setUploadProgress(100)

      // Move to next question or finish
      setTimeout(() => {
        if (currentQuestionIndex + 1 < interview.questions.length) {
          setCurrentQuestionIndex((prev) => prev + 1)
          setStage('recording')
          setUploadProgress(0)
        } else {
          finishInterview()
        }
      }, 800)
    } catch {
      clearInterval(progressInterval)
      setError('Upload failed. Please try again.')
      setStage('recording')
    }
  }

  const finishInterview = async () => {
    if (!interview) return
    try {
      await axios.post(`${API_BASE}/mobile/video-interviews/${interview.interview_id}/complete`)
    } catch {
      // non-fatal
    }
    setStage('done')
  }

  const reRecord = () => {
    chunksRef.current = []
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setIsRecording(false)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-900">
        <div className="text-center text-white">
          <div className="w-12 h-12 border-4 border-purple-400 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p>{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  if (stage === 'error') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-900 px-4">
        <div className="text-center text-white max-w-sm">
          <div className="text-5xl mb-4">❌</div>
          <h2 className="text-xl font-bold mb-2">Interview Not Found</h2>
          <p className="text-gray-400">{error}</p>
        </div>
      </div>
    )
  }

  if (stage === 'done') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-900 px-4">
        <div className="text-center text-white max-w-sm">
          <div className="text-6xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold mb-2">{t('video.done')}</h2>
          <p className="text-gray-400 mt-2">The hiring team will review your responses shortly.</p>
        </div>
      </div>
    )
  }

  // Welcome screen
  if (stage === 'welcome') {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
        <div className="max-w-lg w-full bg-gray-800 rounded-2xl p-8 text-white">
          <div className="text-4xl mb-4 text-center">🎬</div>
          <h1 className="text-2xl font-bold text-center mb-1">{t('video.title')}</h1>
          <p className="text-purple-300 text-center mb-6">
            Hi {interview?.candidate_name}! You're applying for{' '}
            <strong>{interview?.role_name}</strong>.
          </p>

          <div className="bg-gray-700 rounded-xl p-4 mb-6 text-sm text-gray-300 space-y-2">
            <p>📋 {interview?.questions.length} question{interview?.questions.length !== 1 ? 's' : ''} to answer</p>
            <p>⏱️ Each question has a time limit — the recording stops automatically</p>
            <p>🔄 You can re-record any answer before submitting</p>
            <p>🌐 Make sure you're in a quiet, well-lit location</p>
          </div>

          <p className="text-xs text-gray-400 text-center mb-6">{t('video.instructions')}</p>

          {/* Audio-only toggle */}
          {cameraError && (
            <div className="bg-yellow-900/50 border border-yellow-600 rounded-xl px-4 py-3 mb-4 text-sm text-yellow-300">
              Camera not available. Recording audio only.
            </div>
          )}
          <label className="flex items-center gap-3 mb-6 cursor-pointer">
            <input
              type="checkbox"
              checked={audioOnly}
              onChange={(e) => setAudioOnly(e.target.checked)}
              className="w-4 h-4 accent-purple-500"
            />
            <span className="text-sm text-gray-300">Audio-only mode (no camera)</span>
          </label>

          <button
            onClick={() => setStage('recording')}
            className="w-full bg-purple-600 text-white py-4 rounded-2xl font-bold text-lg hover:bg-purple-700 transition"
          >
            Get Started →
          </button>
        </div>
      </div>
    )
  }

  // Uploading screen
  if (stage === 'uploading') {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
        <div className="text-center text-white max-w-sm w-full">
          <div className="text-4xl mb-6">📤</div>
          <h2 className="text-xl font-bold mb-4">{t('video.uploading')}</h2>
          <div className="w-full bg-gray-700 rounded-full h-3 mb-2">
            <div
              className="bg-purple-500 h-3 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-sm text-gray-400">{uploadProgress}%</p>
        </div>
      </div>
    )
  }

  // Recording screen
  const currentQuestion = interview?.questions[currentQuestionIndex]
  const totalQuestions = interview?.questions.length || 0
  const timeLimitForQuestion = currentQuestion?.time_limit_seconds || 120
  const timeProgress = isRecording ? ((timeLimitForQuestion - timeLeft) / timeLimitForQuestion) * 100 : 0
  const timeIsLow = isRecording && timeLeft <= 10

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      {/* Header */}
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between text-white mb-2">
          <span className="text-sm text-gray-400">
            Question {currentQuestionIndex + 1} of {totalQuestions}
          </span>
          {isRecording && (
            <span className={`text-sm font-mono font-bold ${timeIsLow ? 'text-red-400 animate-pulse' : 'text-white'}`}>
              {Math.floor(timeLeft / 60)}:{String(timeLeft % 60).padStart(2, '0')}
            </span>
          )}
        </div>

        {/* Time progress bar */}
        {isRecording && (
          <div className="w-full bg-gray-700 rounded-full h-1.5 mb-3">
            <div
              className={`h-1.5 rounded-full transition-all ${timeIsLow ? 'bg-red-500' : 'bg-purple-500'}`}
              style={{ width: `${timeProgress}%` }}
            />
          </div>
        )}

        {/* Question */}
        <div className="bg-gray-800 rounded-2xl p-4 mb-4">
          <p className="text-sm text-purple-300 mb-1 font-medium">QUESTION</p>
          <p className="text-white text-base leading-relaxed">
            {currentQuestion?.question_text}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            Time limit: {currentQuestion?.time_limit_seconds}s
          </p>
        </div>
      </div>

      {/* Video preview */}
      <div className="flex-1 flex items-center justify-center px-4">
        {!audioOnly ? (
          <div className="w-full max-w-sm aspect-video bg-gray-800 rounded-2xl overflow-hidden">
            <video
              ref={videoRef}
              className="w-full h-full object-cover"
              playsInline
              muted
            />
            {!isRecording && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-gray-500 text-center">
                  <div className="text-4xl mb-2">📷</div>
                  <p className="text-sm">Camera preview</p>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="w-full max-w-sm aspect-video bg-gray-800 rounded-2xl flex items-center justify-center">
            {isRecording ? (
              <div className="text-center">
                <div className="w-16 h-16 bg-red-600 rounded-full flex items-center justify-center animate-pulse mx-auto mb-3">
                  <div className="w-6 h-6 bg-white rounded-full" />
                </div>
                <p className="text-white text-sm font-medium">Recording audio...</p>
              </div>
            ) : (
              <div className="text-center text-gray-500">
                <div className="text-4xl mb-2">🎙️</div>
                <p className="text-sm">Audio only mode</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="px-4 pb-8 pt-4">
        {error && (
          <div className="bg-red-900/50 border border-red-600 rounded-xl px-4 py-3 mb-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {!isRecording && chunksRef.current.length === 0 && (
          <button
            onClick={startRecording}
            className="w-full flex items-center justify-center gap-3 bg-red-600 text-white py-4 rounded-2xl font-bold text-lg hover:bg-red-700 transition"
          >
            <div className="w-5 h-5 bg-white rounded-full" />
            {t('video.startRecording')}
          </button>
        )}

        {isRecording && (
          <button
            onClick={stopRecording}
            className="w-full flex items-center justify-center gap-3 bg-gray-700 text-white py-4 rounded-2xl font-bold text-lg hover:bg-gray-600 transition border-2 border-red-500"
          >
            <div className="w-5 h-5 bg-red-500 rounded" />
            {t('video.stopRecording')}
          </button>
        )}

        {!isRecording && chunksRef.current.length > 0 && (
          <div className="space-y-3">
            <button
              onClick={uploadRecording}
              className="w-full bg-green-600 text-white py-4 rounded-2xl font-bold text-lg hover:bg-green-700 transition"
            >
              Submit Answer & Continue →
            </button>
            <button
              onClick={reRecord}
              className="w-full bg-gray-700 text-white py-3 rounded-2xl font-medium text-sm hover:bg-gray-600 transition"
            >
              {t('video.reRecord')}
            </button>
          </div>
        )}

        {/* Question navigation dots */}
        <div className="flex justify-center gap-2 mt-4">
          {interview?.questions.map((_, i) => (
            <div
              key={i}
              className={`w-2 h-2 rounded-full transition ${
                i === currentQuestionIndex
                  ? 'bg-purple-400'
                  : i < currentQuestionIndex
                  ? 'bg-green-500'
                  : 'bg-gray-600'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
