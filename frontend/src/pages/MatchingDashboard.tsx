/**
 * MatchingDashboard — AI-powered candidate matching & screening features.
 *
 * Tabs:
 *   1. Resume Parser    — parse CV, show fit score, strengths, gaps, skills
 *   2. Rank Candidates  — rank by job requirements, show scored table
 *   3. JD Generator     — generate bias-free job description
 *   4. Reactivation     — surface past candidates with personalized messages
 */

import { Button } from '@/components/ui/button'
import { Card,CardContent,CardDescription,CardHeader,CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { apiClient } from '@/lib/api'
import React,{ useCallback,useRef,useState } from 'react'

// ─── Taxonomy roles (synced with backend) ───────────────────────────────────
const TAXONOMY_ROLES = [
  'chef', 'sous_chef', 'line_cook', 'server', 'bartender',
  'host', 'housekeeping', 'front_desk', 'concierge', 'gm',
]

const EXPERIENCE_LEVELS = ['Entry Level', 'Mid Level', 'Senior', 'Manager', 'Director']

// ─── Shared helpers ──────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 75 ? 'bg-green-100 text-green-800' :
    score >= 50 ? 'bg-yellow-100 text-yellow-800' :
    'bg-red-100 text-red-800'
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${color}`}>
      {score}
    </span>
  )
}

function TagList({ items, color = 'purple' }: { items: string[], color?: string }) {
  const cls = color === 'green'
    ? 'bg-green-100 text-green-800'
    : color === 'red'
    ? 'bg-red-100 text-red-800'
    : 'bg-purple-100 text-purple-800'
  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {items.map((item, i) => (
        <span key={i} className={`text-xs rounded-full px-2 py-1 ${cls}`}>{item}</span>
      ))}
    </div>
  )
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mt-4">
      {msg}
    </div>
  )
}

// ─── Tab 1: Resume Parser ────────────────────────────────────────────────────

function ResumeParserTab() {
  const [inputMode, setInputMode] = useState<'upload' | 'paste'>('upload')
  const [resumeText, setResumeText] = useState('')
  const [jobReqs, setJobReqs] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handlePasteSubmit = async () => {
    if (!resumeText.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await apiClient.post('/matching/parse-resume', {
        resume_text: resumeText,
        job_requirements: jobReqs || undefined,
      })
      setResult(res.data.parsed_profile)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to parse resume')
    } finally {
      setLoading(false)
    }
  }

  const handleFileUpload = async (file: File) => {
    setLoading(true)
    setError('')
    setResult(null)
    setUploadProgress(0)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await apiClient.post('/ai-screening/upload-resume', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
      setResult(res.data.parsed_profile)
      setUploadProgress(100)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to upload and parse resume')
    } finally {
      setLoading(false)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) {
      setSelectedFile(file)
      handleFileUpload(file)
    }
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      handleFileUpload(file)
    }
  }

  const ResultCard = ({ result }: { result: any }) => (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">{result.name}</CardTitle>
            <CardDescription>
              {result.years_total_experience ?? result.experience_years ?? 0} yrs experience ·{' '}
              {result.hospitality_experience_years
                ? `${result.hospitality_experience_years} yrs hospitality`
                : 'No hospitality experience listed'}
            </CardDescription>
          </div>
          <div className="text-center">
            <div className="text-5xl font-bold text-purple-600">{result.fit_score ?? '—'}</div>
            <div className="text-xs text-gray-500 mt-1">Fit Score</div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {(result.roles_held || result.work_history) && (
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Roles Held</p>
            <TagList
              items={
                result.roles_held ||
                (result.work_history || []).map((w: any) => w.title || w).filter(Boolean)
              }
              color="purple"
            />
          </div>
        )}
        <div>
          <p className="text-sm font-semibold text-gray-700 mb-1">Skills</p>
          <TagList items={result.skills || []} color="purple" />
        </div>
        {result.certifications?.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Certifications</p>
            <TagList items={result.certifications} color="purple" />
          </div>
        )}
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-semibold text-green-700 mb-1">Strengths</p>
            <TagList items={result.strengths || []} color="green" />
          </div>
          <div>
            <p className="text-sm font-semibold text-red-700 mb-1">Gaps</p>
            <TagList items={result.gaps || []} color="red" />
          </div>
        </div>
        <div className="rounded-lg bg-gray-50 p-4">
          <p className="text-sm font-semibold text-gray-700 mb-1">AI Reasoning</p>
          <p className="text-sm text-gray-600">{result.reasoning}</p>
        </div>
      </CardContent>
    </Card>
  )

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Resume Parser</CardTitle>
          <CardDescription>Upload a file or paste text to parse a candidate's CV</CardDescription>
          {/* Mode toggle tabs */}
          <div className="flex border-b mt-3">
            {(['upload', 'paste'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setInputMode(mode)}
                className={[
                  'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
                  inputMode === mode
                    ? 'border-purple-600 text-purple-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700',
                ].join(' ')}
              >
                {mode === 'upload' ? 'Upload File' : 'Paste Text'}
              </button>
            ))}
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {inputMode === 'upload' ? (
            <>
              {/* Drag-and-drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                className={[
                  'border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer',
                  isDragging
                    ? 'border-purple-400 bg-purple-50'
                    : 'border-gray-300 hover:border-purple-300 hover:bg-gray-50',
                ].join(' ')}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="mx-auto w-12 h-12 rounded-full bg-purple-50 flex items-center justify-center mb-3">
                  <svg className="w-6 h-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                {selectedFile ? (
                  <p className="text-sm text-gray-700 font-medium">{selectedFile.name}</p>
                ) : (
                  <>
                    <p className="text-sm font-medium text-gray-700">
                      Drop a resume here, or <span className="text-purple-600">browse</span>
                    </p>
                    <p className="text-xs text-gray-400 mt-1">PDF or TXT files supported</p>
                  </>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.text"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </div>

              {/* Upload progress */}
              {loading && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>Uploading & parsing…</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-purple-500 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <textarea
                className="w-full min-h-[200px] rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
                placeholder="Paste CV / resume text here..."
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
              />
              <textarea
                className="w-full min-h-[80px] rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
                placeholder="Optional: paste job requirements to score fit against..."
                value={jobReqs}
                onChange={(e) => setJobReqs(e.target.value)}
              />
              <Button
                onClick={handlePasteSubmit}
                disabled={loading || !resumeText.trim()}
                className="bg-purple-600 hover:bg-purple-700 text-white"
              >
                {loading ? 'Parsing...' : 'Parse Resume'}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {error && <ErrorBox msg={error} />}
      {result && <ResultCard result={result} />}
    </div>
  )
}

// ─── Tab 2: Rank Candidates ──────────────────────────────────────────────────

function RankCandidatesTab() {
  const [jobReqs, setJobReqs] = useState('')
  const [candidateIds, setCandidateIds] = useState('')
  const [useAI, setUseAI] = useState(true)
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    const ids = candidateIds.split(',').map((s) => s.trim()).filter(Boolean)
    if (!jobReqs.trim() || ids.length === 0) return
    setLoading(true)
    setError('')
    setResults([])
    try {
      const res = await apiClient.post('/matching/rank-candidates', {
        job_requirements: jobReqs,
        candidate_ids: ids,
        use_ai: useAI,
      })
      setResults(res.data.ranked_candidates || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Ranking failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Rank Candidates</CardTitle>
          <CardDescription>Score and rank candidates from your database against job requirements</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="w-full min-h-[120px] rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            placeholder="Job requirements (e.g. 3+ years fine dining server, wine knowledge, TIPS cert...)"
            value={jobReqs}
            onChange={(e) => setJobReqs(e.target.value)}
          />
          <Input
            placeholder="Candidate IDs (comma-separated, e.g. uuid1, uuid2, uuid3)"
            value={candidateIds}
            onChange={(e) => setCandidateIds(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={useAI}
              onChange={(e) => setUseAI(e.target.checked)}
              className="rounded"
            />
            Use AI ranking (uncheck for keyword-only fallback)
          </label>
          <Button
            onClick={handleSubmit}
            disabled={loading || !jobReqs.trim() || !candidateIds.trim()}
            className="bg-purple-600 hover:bg-purple-700 text-white"
          >
            {loading ? 'Ranking...' : 'Rank Candidates'}
          </Button>
        </CardContent>
      </Card>

      {error && <ErrorBox msg={error} />}

      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Ranked Results ({results.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="pb-2 pr-4">Rank</th>
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Score</th>
                    <th className="pb-2 pr-4">Strengths</th>
                    <th className="pb-2 pr-4">Gaps</th>
                    <th className="pb-2">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={r.candidate_id || r.id} className="border-b hover:bg-gray-50">
                      <td className="py-3 pr-4 font-bold text-purple-600">#{r.rank}</td>
                      <td className="py-3 pr-4 font-medium">{r.name}</td>
                      <td className="py-3 pr-4"><ScoreBadge score={r.score} /></td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {(r.strengths || []).slice(0, 2).map((s: string, i: number) => (
                            <span key={i} className="text-xs bg-green-100 text-green-800 rounded-full px-2 py-0.5">{s}</span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {(r.gaps || []).slice(0, 2).map((g: string, i: number) => (
                            <span key={i} className="text-xs bg-red-100 text-red-800 rounded-full px-2 py-0.5">{g}</span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 text-gray-600 max-w-xs">{r.reasoning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ─── Tab 3: JD Generator ─────────────────────────────────────────────────────

function JDGeneratorTab() {
  const [role, setRole] = useState('server')
  const [location, setLocation] = useState('')
  const [experienceLevel, setExperienceLevel] = useState('Mid Level')
  const [perks, setPerks] = useState('')
  const [salaryMin, setSalaryMin] = useState('')
  const [salaryMax, setSalaryMax] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const handleSubmit = async () => {
    if (!location.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await apiClient.post('/matching/generate-jd', {
        role,
        location,
        experience_level: experienceLevel,
        perks: perks ? perks.split(',').map((p) => p.trim()).filter(Boolean) : undefined,
        salary_min: salaryMin ? parseInt(salaryMin) : undefined,
        salary_max: salaryMax ? parseInt(salaryMax) : undefined,
      })
      setResult(res.data.job_description)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'JD generation failed')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = () => {
    if (result?.full_text) {
      navigator.clipboard.writeText(result.full_text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Job Description Generator</CardTitle>
          <CardDescription>Generate a bias-free, inclusive hospitality job description</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Role</label>
              <select
                className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                {TAXONOMY_ROLES.map((r) => (
                  <option key={r} value={r}>{r.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Location</label>
              <Input
                placeholder="e.g. New York, NY"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Experience Level</label>
              <select
                className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={experienceLevel}
                onChange={(e) => setExperienceLevel(e.target.value)}
              >
                {EXPERIENCE_LEVELS.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Perks (comma-separated)</label>
              <Input
                placeholder="e.g. health insurance, meal staff, tips"
                value={perks}
                onChange={(e) => setPerks(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Salary Min ($/yr)</label>
              <Input
                type="number"
                placeholder="e.g. 45000"
                value={salaryMin}
                onChange={(e) => setSalaryMin(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Salary Max ($/yr)</label>
              <Input
                type="number"
                placeholder="e.g. 65000"
                value={salaryMax}
                onChange={(e) => setSalaryMax(e.target.value)}
              />
            </div>
          </div>
          <Button
            onClick={handleSubmit}
            disabled={loading || !location.trim()}
            className="bg-purple-600 hover:bg-purple-700 text-white"
          >
            {loading ? 'Generating...' : 'Generate Job Description'}
          </Button>
        </CardContent>
      </Card>

      {error && <ErrorBox msg={error} />}

      {result && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">{result.title}</CardTitle>
              <Button
                onClick={handleCopy}
                className="bg-gray-100 text-gray-700 hover:bg-gray-200 text-sm px-3 py-1.5"
              >
                {copied ? 'Copied!' : 'Copy JD'}
              </Button>
            </div>
            <CardDescription>{result.summary}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-semibold text-gray-700 mb-2">Responsibilities</p>
                <ul className="space-y-1 text-sm text-gray-600">
                  {(result.responsibilities || []).map((r: string, i: number) => (
                    <li key={i} className="flex gap-2"><span className="text-purple-400">•</span>{r}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-700 mb-2">Requirements</p>
                <ul className="space-y-1 text-sm text-gray-600">
                  {(result.requirements || []).map((r: string, i: number) => (
                    <li key={i} className="flex gap-2"><span className="text-purple-400">•</span>{r}</li>
                  ))}
                </ul>
              </div>
            </div>
            {result.nice_to_have?.length > 0 && (
              <div>
                <p className="text-sm font-semibold text-gray-700 mb-1">Nice to Have</p>
                <TagList items={result.nice_to_have} color="purple" />
              </div>
            )}
            {result.perks?.length > 0 && (
              <div>
                <p className="text-sm font-semibold text-gray-700 mb-1">Perks & Benefits</p>
                <TagList items={result.perks} color="green" />
              </div>
            )}
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-sm font-semibold text-gray-700">Compensation</p>
              <p className="text-sm text-gray-600 mt-1">{result.salary_info}</p>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-700 mb-2">Full Job Description</p>
              <pre className="whitespace-pre-wrap text-sm text-gray-600 bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto font-sans">
                {result.full_text}
              </pre>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ─── Tab 4: Reactivation ─────────────────────────────────────────────────────

function ReactivationTab() {
  const [jobReqs, setJobReqs] = useState('')
  const [limit, setLimit] = useState('20')
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!jobReqs.trim()) return
    setLoading(true)
    setError('')
    setResults([])
    try {
      const res = await apiClient.post('/matching/reactivation-candidates', {
        job_requirements: jobReqs,
        limit: parseInt(limit) || 20,
      })
      setResults(res.data.reactivation_candidates || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Reactivation fetch failed')
    } finally {
      setLoading(false)
    }
  }

  const likelihoodColor = (l: string) =>
    l === 'high' ? 'bg-green-100 text-green-800' :
    l === 'medium' ? 'bg-yellow-100 text-yellow-800' :
    'bg-red-100 text-red-800'

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Talent Reactivation</CardTitle>
          <CardDescription>
            Surface past candidates from your database who match a new open role and generate
            personalized re-engagement messages.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="w-full min-h-[120px] rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            placeholder="Describe the new open role and requirements..."
            value={jobReqs}
            onChange={(e) => setJobReqs(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <div className="w-32">
              <label className="text-xs font-medium text-gray-600 mb-1 block">Max results</label>
              <Input
                type="number"
                min={1}
                max={50}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              />
            </div>
            <div className="pt-5">
              <Button
                onClick={handleSubmit}
                disabled={loading || !jobReqs.trim()}
                className="bg-purple-600 hover:bg-purple-700 text-white"
              >
                {loading ? 'Scoring...' : 'Find Reactivation Candidates'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {error && <ErrorBox msg={error} />}

      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Reactivation Candidates ({results.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {results.map((r, i) => (
                <div key={r.candidate_id || i} className="rounded-lg border p-4 hover:bg-gray-50">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="font-semibold text-gray-900">{r.name}</span>
                        {r.email && <span className="text-xs text-gray-500">{r.email}</span>}
                        {r.engagement_likelihood && (
                          <span className={`text-xs rounded-full px-2 py-0.5 font-medium ${likelihoodColor(r.engagement_likelihood)}`}>
                            {r.engagement_likelihood} likelihood
                          </span>
                        )}
                      </div>
                      {r.last_active && (
                        <p className="text-xs text-gray-400 mt-0.5">
                          Last active: {new Date(r.last_active).toLocaleDateString()}
                        </p>
                      )}
                      <p className="text-sm text-gray-600 mt-2">{r.fit_reasoning}</p>
                    </div>
                    <div className="text-center flex-shrink-0">
                      <div className="text-3xl font-bold text-purple-600">{r.reactivation_score}</div>
                      <div className="text-xs text-gray-400">score</div>
                    </div>
                  </div>
                  <div className="mt-3">
                    <button
                      onClick={() => setExpanded(expanded === (r.candidate_id || String(i)) ? null : (r.candidate_id || String(i)))}
                      className="text-xs text-purple-600 hover:text-purple-800 font-medium"
                    >
                      {expanded === (r.candidate_id || String(i)) ? 'Hide message' : 'Show re-engagement message'}
                    </button>
                    {expanded === (r.candidate_id || String(i)) && r.personalized_message && (
                      <div className="mt-2 rounded-lg bg-purple-50 border border-purple-100 p-3">
                        <p className="text-xs font-semibold text-purple-700 mb-1">Personalized Re-engagement Message</p>
                        <p className="text-sm text-gray-700">{r.personalized_message}</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ─── Main dashboard ──────────────────────────────────────────────────────────

type Tab = 'resume' | 'rank' | 'jd' | 'reactivation'

const TABS: { id: Tab; label: string }[] = [
  { id: 'resume', label: 'Resume Parser' },
  { id: 'rank', label: 'Rank Candidates' },
  { id: 'jd', label: 'JD Generator' },
  { id: 'reactivation', label: 'Reactivation' },
]

export const MatchingDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('resume')

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-bold">AI Matching</h1>
        <p className="mt-1 opacity-90 text-sm">
          AI-powered candidate matching, resume parsing, and talent reactivation
        </p>
      </div>

      {/* Tab nav */}
      <div className="border-b border-gray-200 bg-white sticky top-0 z-10">
        <nav className="flex overflow-x-auto max-w-7xl mx-auto px-4 sm:px-6 lg:px-8" aria-label="Tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={[
                'whitespace-nowrap py-4 px-6 text-sm font-medium border-b-2 transition-colors',
                activeTab === tab.id
                  ? 'border-purple-600 text-purple-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
              ].join(' ')}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'resume' && <ResumeParserTab />}
        {activeTab === 'rank' && <RankCandidatesTab />}
        {activeTab === 'jd' && <JDGeneratorTab />}
        {activeTab === 'reactivation' && <ReactivationTab />}
      </div>
    </div>
  )
}
