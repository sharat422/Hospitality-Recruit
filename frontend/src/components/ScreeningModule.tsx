/**
 * Screening component (Module 1: AI candidate qualification).
 * Pain #1: 100-500 apps/role, 65% screening time, reduce unqualified.
 */

import { Button } from '@/components/ui/button'
import { Card,CardContent,CardDescription,CardHeader,CardTitle } from '@/components/ui/card'
import { useBulkScreenCandidates,useCandidatesForJob } from '@/hooks/useApiFunctions'
import { AlertCircle,AlertTriangle,CheckCircle } from 'lucide-react'
import { useState } from 'react'

export function ScreeningModule({ jobId }: { jobId: string }) {
  const { data: candidates, isLoading } = useCandidatesForJob(jobId)
  const bulkMutation = useBulkScreenCandidates()
  const [jobRequirements, setJobRequirements] = useState('')

  const handleBulkScreen = async () => {
    if (!jobRequirements) {
      alert('Please enter job requirements')
      return
    }
    await bulkMutation.mutateAsync({ jobId, jobRequirements })
  }

  if (isLoading) return <div>Loading candidates...</div>

  const unscreenedCount = candidates?.candidates?.filter((c: any) => !c.qualified).length || 0
  const qualifiedCount = candidates?.candidates?.filter((c: any) => c.qualified).length || 0

  return (
    <div className="space-y-6">
      {/* Job Requirements Input */}
      <Card>
        <CardHeader>
          <CardTitle>Screening Setup (Pain #1: Reduce 65% Screening Time)</CardTitle>
          <CardDescription>Enter job requirements for AI screening</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <textarea
            value={jobRequirements}
            onChange={(e) => setJobRequirements(e.target.value)}
            placeholder="e.g., 2+ years server experience, food handler cert, available weekends"
            className="w-full h-24 p-2 border rounded"
          />
          <Button
            onClick={handleBulkScreen}
            disabled={bulkMutation.isPending}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {bulkMutation.isPending ? 'Screening...' : `Bulk Screen ${unscreenedCount} Candidates`}
          </Button>
        </CardContent>
      </Card>

      {/* Results Summary */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Pre-screened</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold text-green-600">{qualifiedCount}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Pending</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold text-yellow-600">{unscreenedCount}</CardContent>
        </Card>
      </div>

      {/* Candidate List */}
      <Card>
        <CardHeader>
          <CardTitle>Candidates</CardTitle>
          <CardDescription>Click to view screening details (Pain #1: fast triage)</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {candidates?.candidates?.map((candidate: any) => (
              <div key={candidate.id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50">
                <div>
                  <p className="font-medium">{candidate.first_name} {candidate.last_name}</p>
                  <p className="text-sm text-gray-500">{candidate.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  {candidate.qualified ? (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  ) : candidate.screening_result ? (
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-yellow-600" />
                  )}
                  {candidate.screening_result && (
                    <div className="text-right">
                      <p className="text-sm font-bold">{candidate.screening_result.ai_score}</p>
                      <p className="text-xs text-gray-500">via AI</p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
