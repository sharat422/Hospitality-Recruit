/**
 * ATS Settings Page Component
 *
 * Features:
 * - Connect/disconnect ATS via OAuth
 * - View synced jobs from ATS
 * - Manually trigger job sync
 * - View sync status and logs
 * - Configure sync settings
 *
 * Supported ATS: Bullhorn, iCIMS, Greenhouse, Workable, SmartRecruiters, etc
 * (50+ platforms via Merge.dev)
 */

'use client';

import {
AlertDialog,
AlertDialogAction,
AlertDialogCancel,
AlertDialogContent,
AlertDialogDescription,
AlertDialogTitle,
AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import {
Button,
} from '@/components/ui/button';
import {
Card,
CardContent,
CardDescription,
CardHeader,
CardTitle
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
Tabs,
TabsContent,
TabsList,
TabsTrigger
} from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { apiClient as api } from '@/lib/api';
import {
AlertCircle,
Briefcase,
Link as LinkIcon,
Loader,
RefreshCw,
TrendingUp,
Unlink
} from 'lucide-react';
import React,{ useEffect,useState } from 'react';



interface ATSStatus {
  id: string;
  provider: string;
  is_connected: boolean;
  last_sync: string;
  next_sync: string;
  synced_jobs: number;
  synced_candidates: number;
  pending_syncs: number;
}

interface SyncedJob {
  id: string;
  title: string;
  department: string;
  location: string;
  ats_status: string;
  hiring_manager_name: string;
  synced_at: string;
}

interface SyncLog {
  id: string;
  operation_type: string;
  status: string;
  records_succeeded: number;
  records_failed: number;
  created_at: string;
  error_message?: string;
}


// ============================================================================
// Sub-Components
// ============================================================================

/**
 * Connection Status Card
 */
const ConnectionStatusCard: React.FC<{
  status: ATSStatus;
  onConnect: () => void;
  onDisconnect: (id: string) => void;
  onSyncJobs: (id: string) => void;
  isSyncing: boolean;
}> = ({ status, onConnect, onDisconnect, onSyncJobs, isSyncing }) => {
  return (
    <Card className="border-2">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-blue-600" />
            <div>
              <CardTitle className="text-lg capitalize">
                {status.provider}
              </CardTitle>
              <CardDescription className="text-xs">
                ATS Integration
              </CardDescription>
            </div>
          </div>
          <Badge
            variant={status.is_connected ? 'default' : 'secondary'}
            className="capitalize"
          >
            {status.is_connected ? 'Connected' : 'Disconnected'}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {status.is_connected ? (
          <>
            {/* Sync Status */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-blue-50 p-3 rounded">
                <p className="text-xs text-gray-600">Synced Jobs</p>
                <p className="text-2xl font-bold text-blue-600">
                  {status.synced_jobs}
                </p>
              </div>

              <div className="bg-green-50 p-3 rounded">
                <p className="text-xs text-gray-600">Candidates</p>
                <p className="text-2xl font-bold text-green-600">
                  {status.synced_candidates}
                </p>
              </div>

              <div className="bg-yellow-50 p-3 rounded">
                <p className="text-xs text-gray-600">Pending</p>
                <p className="text-2xl font-bold text-yellow-600">
                  {status.pending_syncs}
                </p>
              </div>
            </div>

            {/* Last Sync */}
            <div className="text-xs text-gray-600">
              <p className="font-semibold">Last Sync</p>
              {status.last_sync ? (
                <p>{new Date(status.last_sync).toLocaleString()}</p>
              ) : (
                <p className="text-gray-400">Never synced</p>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <Button
                size="sm"
                className="flex-1"
                onClick={() => onSyncJobs(status.id)}
                disabled={isSyncing}
              >
                {isSyncing ? (
                  <>
                    <Loader className="w-4 h-4 mr-2 animate-spin" />
                    Syncing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Sync Now
                  </>
                )}
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="flex-1"
                  >
                    <Unlink className="w-4 h-4 mr-2" />
                    Disconnect
                  </Button>
                </AlertDialogTrigger>

                <AlertDialogContent>
                  <AlertDialogTitle>Disconnect ATS?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Disconnecting will stop syncing jobs and candidates.
                    Existing data will be preserved.
                  </AlertDialogDescription>

                  <div className="flex gap-3 justify-end">
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      className="bg-red-600 hover:bg-red-700"
                      onClick={() => onDisconnect(status.id)}
                    >
                      Disconnect
                    </AlertDialogAction>
                  </div>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </>
        ) : (
          <>
            <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
              <div className="flex gap-2">
                <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-semibold text-yellow-900">Not Connected</p>
                  <p className="text-yellow-800 text-xs mt-1">
                    Connect your {status.provider} account to sync jobs and candidates.
                  </p>
                </div>
              </div>
            </div>

            <Button
              onClick={onConnect}
              size="sm"
              className="w-full"
            >
              <LinkIcon className="w-4 h-4 mr-2" />
              Connect {status.provider}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
};


/**
 * Synced Jobs List
 */
const SyncedJobsList: React.FC<{
  jobs: SyncedJob[];
  isLoading: boolean;
}> = ({ jobs, isLoading }) => {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map(i => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    );
  }

  if (!jobs.length) {
    return (
      <div className="text-center py-12">
        <Briefcase className="w-12 h-12 text-gray-300 mx-auto mb-3" />
        <p className="text-gray-500">No synced jobs yet</p>
        <p className="text-xs text-gray-400">
          Sync your ATS to pull job openings
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {jobs.map(job => (
        <Card key={job.id}>
          <CardContent className="pt-6">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h4 className="font-semibold">{job.title}</h4>
                <p className="text-sm text-gray-600 mt-1">
                  {job.department} {job.location && `• ${job.location}`}
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="outline" className="text-xs">
                    {job.ats_status}
                  </Badge>
                  <span className="text-xs text-gray-500">
                    Synced {new Date(job.synced_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
              {job.hiring_manager_name && (
                <div className="text-right text-xs">
                  <p className="text-gray-600">Hiring Manager</p>
                  <p className="font-medium">{job.hiring_manager_name}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};


/**
 * Sync Logs/History
 */
const SyncLogsTable: React.FC<{ logs: SyncLog[] }> = ({ logs }) => {
  if (!logs.length) {
    return (
      <div className="text-center py-8">
        <p className="text-gray-500">No sync operations yet</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b">
          <tr>
            <th className="text-left py-2 px-3">Operation</th>
            <th className="text-left py-2 px-3">Status</th>
            <th className="text-center py-2 px-3">Success</th>
            <th className="text-center py-2 px-3">Failed</th>
            <th className="text-left py-2 px-3">Time</th>
          </tr>
        </thead>
        <tbody>
          {logs.map(log => (
            <tr
              key={log.id}
              className="border-b hover:bg-gray-50"
            >
              <td className="py-3 px-3 capitalize">
                {log.operation_type.replace(/_/g, ' ')}
              </td>
              <td className="py-3 px-3">
                <Badge
                  variant={log.status === 'success' ? 'default' : 'destructive'}
                >
                  {log.status}
                </Badge>
              </td>
              <td className="py-3 px-3 text-center text-green-600 font-semibold">
                {log.records_succeeded}
              </td>
              <td className="py-3 px-3 text-center text-red-600 font-semibold">
                {log.records_failed}
              </td>
              <td className="py-3 px-3 text-xs text-gray-600">
                {new Date(log.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};


// ============================================================================
// Main Settings Component
// ============================================================================

export const ATSSettings: React.FC = () => {
  const { toast } = useToast();
  const [statuses, setStatuses] = useState<ATSStatus[]>([]);
  const [jobs, setJobs] = useState<SyncedJob[]>([]);
  const [logs, setLogs] = useState<SyncLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);

        // Get ATS status
        const statusRes = await api.get('/ats/status');
        setStatuses(statusRes.data.statuses);

        // Get synced jobs
        const jobsRes = await api.get('/ats/jobs');
        setJobs(jobsRes.data.items);

        // Get sync logs
        const logsRes = await api.get('/ats/sync-logs');
        setLogs(logsRes.data.items);
      } catch (error) {
        console.error('Failed to fetch ATS data:', error);
        toast({
          title: 'Error',
          description: 'Failed to load ATS settings',
          variant: 'destructive'
        });
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [toast]);

  // Handle OAuth connection
  const handleConnect = async () => {
    try {
      const response = await api.get('/ats/oauth-url');
      
      // Redirect to OAuth
      window.location.href = response.data.oauth_url;
    } catch (error) {
      console.error('Failed to initiate OAuth:', error);
      toast({
        title: 'Error',
        description: 'Failed to start ATS connection',
        variant: 'destructive'
      });
    }
  };

  // Handle disconnect
  const handleDisconnect = async (configId: string) => {
    try {
      await api.post('/ats/disconnect', { ats_config_id: configId });

      // Refresh data
      const statusRes = await api.get('/ats/status');
      setStatuses(statusRes.data.statuses);

      toast({
        title: 'Success',
        description: 'ATS disconnected'
      });
    } catch (error) {
      console.error('Failed to disconnect:', error);
      toast({
        title: 'Error',
        description: 'Failed to disconnect ATS',
        variant: 'destructive'
      });
    }
  };

  // Handle job sync
  const handleSyncJobs = async (configId: string) => {
    try {
      setIsSyncing(configId);

      const response = await api.post('/ats/jobs/sync', {
        ats_config_id: configId
      });

      // Refresh jobs
      const jobsRes = await api.get('/ats/jobs');
      setJobs(jobsRes.data.items);

      toast({
        title: 'Success',
        description: response.data.message
      });
    } catch (error) {
      console.error('Sync failed:', error);
      toast({
        title: 'Error',
        description: 'Job sync failed',
        variant: 'destructive'
      });
    } finally {
      setIsSyncing(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <Briefcase className="w-8 h-8 text-blue-600" />
          ATS Integrations
        </h1>
        <p className="text-gray-600 mt-2">
          Connect your Applicant Tracking System via Merge.dev.
          Sync 50+ ATS platforms: Bullhorn, iCIMS, Greenhouse, Workable, SmartRecruiters, and more.
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="jobs">Synced Jobs</TabsTrigger>
          <TabsTrigger value="logs">Sync History</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2].map(i => (
                <Skeleton key={i} className="h-56" />
              ))}
            </div>
          ) : statuses.length > 0 ? (
            <div className="space-y-3">
              {statuses.map(status => (
                <ConnectionStatusCard
                  key={status.id}
                  status={status}
                  onConnect={handleConnect}
                  onDisconnect={handleDisconnect}
                  onSyncJobs={handleSyncJobs}
                  isSyncing={isSyncing === status.id}
                />
              ))}
            </div>
          ) : (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Briefcase className="w-12 h-12 text-gray-300 mb-4" />
                <h3 className="font-semibold text-lg">No ATS Connected</h3>
                <p className="text-gray-500 text-sm mt-2">
                  Connect your ATS to sync jobs and candidates automatically.
                </p>
                <Button
                  onClick={handleConnect}
                  className="mt-4"
                >
                  <LinkIcon className="w-4 h-4 mr-2" />
                  Connect ATS
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Info Banner */}
          <Card className="bg-blue-50 border-blue-200">
            <CardContent className="pt-6">
              <div className="flex gap-3">
                <TrendingUp className="w-5 h-5 text-blue-600 flex-shrink-0" />
                <div className="text-sm">
                  <p className="font-semibold text-blue-900">Benefits of ATS Sync</p>
                  <ul className="text-blue-800 mt-2 space-y-1 text-xs">
                    <li>• Pull jobs automatically from your ATS</li>
                    <li>• Push screened candidates back to ATS</li>
                    <li>• Keep pipeline stages in sync</li>
                    <li>• Real-time webhook updates</li>
                    <li>• Single source of truth for candidate data</li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Jobs Tab */}
        <TabsContent value="jobs">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Synced Jobs</CardTitle>
                <Badge variant="outline">{jobs.length} total</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <SyncedJobsList
                jobs={jobs}
                isLoading={isLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Logs Tab */}
        <TabsContent value="logs">
          <Card>
            <CardHeader>
              <CardTitle>Sync History</CardTitle>
              <CardDescription>
                Recent synchronization operations
              </CardDescription>
            </CardHeader>
            <CardContent>
              <SyncLogsTable logs={logs} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ATSSettings;
