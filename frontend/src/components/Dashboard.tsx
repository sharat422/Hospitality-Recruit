/**
 * Dashboard component (Module 6: Manager burnout reduction).
 * Real-time metrics, pipeline visualization, alerts.
 * Pain #3: Manager burnout & slow fills.
 */

import { Card,CardContent,CardDescription,CardHeader,CardTitle } from '@/components/ui/card'
import { useCostPerHire,useManagerDashboard,useNoShowAnalysis } from '@/hooks/useApiFunctions'
import { AlertCircle,Clock,TrendingUp,Users } from 'lucide-react'
import { Bar,BarChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis } from 'recharts'

export function Dashboard() {
  const { data: dashboardData, isLoading: isDashboardLoading } = useManagerDashboard()
  const { data: noShowData } = useNoShowAnalysis()
  const { data: costData } = useCostPerHire()

  if (isDashboardLoading) return <div>Loading dashboard...</div>

  const pipelineData = dashboardData?.pipeline_summary || []

  return (
    <div className="space-y-6">
      {/* Top KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPICard
          title="Total Applications"
          value={dashboardData?.total_applications || 0}
          icon={<Users className="w-4 h-4" />}
          pain="Pain #1: 100-500 apps/role"
        />
        <KPICard
          title="Qualified Candidates"
          value={dashboardData?.total_qualified || 0}
          icon={<TrendingUp className="w-4 h-4" />}
          subtext={`${((dashboardData?.total_qualified / dashboardData?.total_applications) * 100 || 0).toFixed(1)}% qualification rate`}
        />
        <KPICard
          title="Avg Fill Time"
          value={`${costData?.avg_fill_time_days?.toFixed(1) || 0} days`}
          icon={<Clock className="w-4 h-4" />}
          subtext={`vs ${costData?.industry_average_days} day industry avg`}
        />
        <KPICard
          title="No-Show Rate"
          value={`${noShowData?.no_show_rate_percent?.toFixed(1) || 0}%`}
          icon={<AlertCircle className="w-4 h-4" />}
          pain="Pain #2: 70% no-show norm"
        />
      </div>

      {/* Pipeline Visualization */}
      <Card>
        <CardHeader>
          <CardTitle>Pipeline by Stage (Pain #3: Visibility)</CardTitle>
          <CardDescription>Candidate flow from applied → filled</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={pipelineData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="stage" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Alerts */}
      <Card className="border-orange-200 bg-orange-50">
        <CardHeader>
          <CardTitle className="text-orange-900">Alerts (Pain #3: Burnout Prevention)</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm text-orange-800">
            {dashboardData?.alerts?.map((alert: string, idx: number) => (
              <li key={idx}>•  {alert}</li>
            )) || (
              <li>No alerts - all systems nominal</li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

function KPICard({ title, value, icon, subtext, pain }: any) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {subtext && <p className="text-xs text-gray-500 mt-1">{subtext}</p>}
        {pain && <p className="text-xs text-red-500 mt-1">{pain}</p>}
      </CardContent>
    </Card>
  )
}
