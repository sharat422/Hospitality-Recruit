/**
 * React Query hooks for HospRecruit AI modules.
 * TanStack Query v5 for server state management.
 * Pain points: real-time data, caching, background syncing.
 */

import { apiClient } from '@/lib/api'
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query'

// ============================================================================
// Module 1: Candidate Screening
// ============================================================================

export const useCandidatesForJob = (jobId: string) => {
  return useQuery({
    queryKey: ['candidates', jobId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/candidates/job/${jobId}`)
      return data
    },
    staleTime: 5 * 60 * 1000, // 5 min
  })
}

export const useQualifiedCandidates = (jobId: string) => {
  return useQuery({
    queryKey: ['candidates', jobId, 'qualified'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/candidates/job/${jobId}/qualified`)
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export const useScreenCandidate = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      candidateId,
      jobRequirements,
      useClaude = true,
    }: {
      candidateId: string
      jobRequirements: string
      useClaude?: boolean
    }) => {
      const { data } = await apiClient.post(
        `/screening/${candidateId}/screen`,
        { job_requirements: jobRequirements, use_claude: useClaude }
      )
      return data
    },
    onSuccess: () => {
      // Invalidate candidate and screening stats to refetch
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      queryClient.invalidateQueries({ queryKey: ['screening'] })
    },
  })
}

export const useBulkScreenCandidates = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      jobId,
      jobRequirements,
    }: {
      jobId: string
      jobRequirements: string
    }) => {
      const { data } = await apiClient.post(`/screening/job/${jobId}/bulk-screen`, {
        job_requirements: jobRequirements,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['screening'] })
    },
  })
}

// ============================================================================
// Module 2: Shift Matching
// ============================================================================

export const useOpenShifts = () => {
  return useQuery({
    queryKey: ['shifts', 'open'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/shifts/open`)
      return data
    },
    staleTime: 10 * 60 * 1000,
  })
}

export const useShiftMatches = (candidateId: string) => {
  return useQuery({
    queryKey: ['shiftMatches', candidateId],
    queryFn: async () => {
      const { data } = await apiClient.post(`/shifts/${candidateId}/match`)
      return data
    },
    enabled: !!candidateId,
  })
}

// ============================================================================
// Module 6: Dashboard Analytics
// ============================================================================

export const useManagerDashboard = () => {
  return useQuery({
    queryKey: ['analytics', 'dashboard'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/analytics/manager-dashboard`)
      return data
    },
    staleTime: 2 * 60 * 1000, // Update every 2 min for real-time feel
    refetchInterval: 2 * 60 * 1000,
  })
}

export const useJobPipeline = (jobId: string) => {
  return useQuery({
    queryKey: ['analytics', jobId, 'pipeline'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/analytics/job/${jobId}/pipeline`)
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export const useNoShowAnalysis = () => {
  return useQuery({
    queryKey: ['analytics', 'no-show'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/analytics/no-show-analysis`)
      return data
    },
    staleTime: 30 * 60 * 1000,
  })
}

export const useCostPerHire = () => {
  return useQuery({
    queryKey: ['analytics', 'cost-per-hire'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/analytics/cost-per-hire`)
      return data
    },
    staleTime: 60 * 60 * 1000,
  })
}

// ============================================================================
// Module 5: Onboarding
// ============================================================================

export const useOnboardingStatus = (candidateId: string) => {
  return useQuery({
    queryKey: ['onboarding', candidateId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/onboarding/${candidateId}/status`)
      return data
    },
    enabled: !!candidateId,
    staleTime: 5 * 60 * 1000,
  })
}

export const useInitOnboarding = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      candidateId,
      jobId,
      jobRole,
    }: {
      candidateId: string
      jobId: string
      jobRole: string
    }) => {
      const { data } = await apiClient.post(
        `/onboarding/${candidateId}/${jobId}/init-flow`,
        { job_role: jobRole }
      )
      return data
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['onboarding', variables.candidateId],
      })
    },
  })
}
