/**
 * MatchScoreCard — Reusable component showing detailed match score breakdown.
 */

import { Button } from '@/components/ui/button'
import { Card,CardContent,CardHeader } from '@/components/ui/card'

interface Candidate {
  id?: string
  name?: string
  first_name?: string
  last_name?: string
  email?: string
  parsed_skills?: string[]
}

interface JobRole {
  id?: string
  title?: string
  location?: string
  required_skills?: string[]
}

interface Match {
  overall_score: number
  skill_match_score: number
  soft_skill_score: number
  experience_score: number
  cross_industry_score: number
  match_reasoning?: string
  strengths?: string[]
  gaps?: string[]
}

interface MatchScoreCardProps {
  candidate: Candidate
  jobRole: JobRole
  match: Match
  onShortlist?: () => void
  onReject?: () => void
}

function CircleScore({ score }: { score: number }) {
  const color =
    score >= 75
      ? 'text-green-600 border-green-400'
      : score >= 50
      ? 'text-amber-600 border-amber-400'
      : 'text-red-600 border-red-400'

  const bgColor =
    score >= 75
      ? 'bg-green-50'
      : score >= 50
      ? 'bg-amber-50'
      : 'bg-red-50'

  return (
    <div
      className={`flex items-center justify-center w-24 h-24 rounded-full border-4 ${color} ${bgColor} flex-shrink-0`}
    >
      <div className="text-center">
        <div className={`text-2xl font-bold ${color.split(' ')[0]}`}>{Math.round(score)}</div>
        <div className="text-xs text-gray-500">/ 100</div>
      </div>
    </div>
  )
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const barColor =
    score >= 75
      ? 'bg-green-500'
      : score >= 50
      ? 'bg-amber-500'
      : 'bg-red-500'

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-600">{label}</span>
        <span className="font-semibold text-gray-800">{Math.round(score)}</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
    </div>
  )
}

export function MatchScoreCard({
  candidate,
  jobRole,
  match,
  onShortlist,
  onReject,
}: MatchScoreCardProps) {
  const candidateName =
    candidate.name ||
    `${candidate.first_name || ''} ${candidate.last_name || ''}`.trim() ||
    'Unknown Candidate'

  const requiredSkills = jobRole.required_skills || []
  const candidateSkills = candidate.parsed_skills || []
  const candidateSkillsLower = candidateSkills.map((s) => s.toLowerCase())

  const matchedSkills = requiredSkills.filter((s) =>
    candidateSkillsLower.some((cs) => cs.includes(s.toLowerCase()) || s.toLowerCase().includes(cs))
  )
  const missingSkills = requiredSkills.filter((s) => !matchedSkills.includes(s))

  return (
    <Card className="w-full">
      <CardHeader className="pb-4">
        <div className="flex items-start gap-4">
          <CircleScore score={match.overall_score} />
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-bold text-gray-900 truncate">{candidateName}</h3>
            {candidate.email && (
              <p className="text-sm text-gray-500 truncate">{candidate.email}</p>
            )}
            <p className="text-sm text-purple-600 font-medium mt-1">
              {jobRole.title}
              {jobRole.location ? ` · ${jobRole.location}` : ''}
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Score bars */}
        <div className="space-y-3">
          <ScoreBar label="Skill Match" score={match.skill_match_score} />
          <ScoreBar label="Soft Skills" score={match.soft_skill_score} />
          <ScoreBar label="Experience" score={match.experience_score} />
          <ScoreBar label="Cross-Industry" score={match.cross_industry_score} />
        </div>

        {/* Why this score */}
        {match.match_reasoning && (
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Why this score
            </p>
            <p className="text-sm text-gray-700 leading-relaxed">{match.match_reasoning}</p>
          </div>
        )}

        {/* Skill tags */}
        {(requiredSkills.length > 0 || (match.strengths && match.strengths.length > 0)) && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Skill breakdown
            </p>
            <div className="flex flex-wrap gap-2">
              {matchedSkills.map((skill, i) => (
                <span
                  key={`matched-${i}`}
                  className="text-xs px-2 py-1 rounded-full bg-green-100 text-green-800 border border-green-200"
                >
                  {skill}
                </span>
              ))}
              {(match.gaps || missingSkills).slice(0, 5).map((skill, i) => (
                <span
                  key={`missing-${i}`}
                  className="text-xs px-2 py-1 rounded-full bg-red-100 text-red-800 border border-red-200"
                >
                  {skill}
                </span>
              ))}
            </div>
            {(matchedSkills.length > 0 || missingSkills.length > 0) && (
              <p className="text-xs text-gray-400">
                <span className="text-green-600">{matchedSkills.length} matched</span>
                {missingSkills.length > 0 && (
                  <span className="text-red-500"> · {missingSkills.length} missing</span>
                )}
              </p>
            )}
          </div>
        )}

        {/* Actions */}
        {(onShortlist || onReject) && (
          <div className="flex gap-3 pt-2">
            {onShortlist && (
              <Button
                onClick={onShortlist}
                className="flex-1 bg-green-600 hover:bg-green-700 text-white text-sm"
              >
                Shortlist
              </Button>
            )}
            {onReject && (
              <Button
                onClick={onReject}
                className="flex-1 bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 text-sm"
              >
                Reject
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
