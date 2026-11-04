/**
React Billing Dashboard
Subscription status, usage, invoices, and billing management
*/

import { apiClient as api } from '@/lib/api';
import {
Add as AddIcon,
Cancel as CancelIcon,
Download as DownloadIcon
} from '@mui/icons-material';
import {
Alert,
Box,
Button,
Card,
CardContent,
CardHeader,
Chip,
CircularProgress,
Container,
Dialog,
DialogActions,
DialogContent,
DialogTitle,
Grid,
LinearProgress,
Tab,
Table,
TableBody,
TableCell,
TableContainer,
TableHead,
TableRow,
Tabs,
Typography,
} from '@mui/material';
import React,{ useEffect,useState } from 'react';

// ============================================================================
// TYPES
// ============================================================================

interface BillingStatus {
  tier: string;
  tier_display: string;
  subscription_status?: string;
  period_start?: string;
  period_end?: string;
  trial: {
    status: string;
    started_at?: string;
    ends_at?: string;
  };
  usage: {
    roles_per_month: { limit: number; used: number; remaining: number };
    video_interviews_per_month: { limit: number; used: number; remaining: number };
    ai_credits_per_month: { limit: number; used: number; remaining: number };
  };
}

interface Invoice {
  id: string;
  stripe_invoice_id: string;
  amount_total: number;
  amount_paid: number;
  currency: string;
  issue_date: string;
  status: string;
  paid_date?: string;
  pdf_url?: string;
}

// ============================================================================
// BILLING DASHBOARD
// ============================================================================

export const BillingDashboard: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);
  const [billingStatus, setBillingStatus] = useState<BillingStatus | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const [showCreditDialog, setShowCreditDialog] = useState(false);
  const [creditAmount, setCreditAmount] = useState(100);
  const [canceling, setCanceling] = useState(false);
  const [creditLoading, setCreditLoading] = useState(false);

  useEffect(() => {
    fetchBillingData();
    const interval = setInterval(fetchBillingData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const fetchBillingData = async () => {
    try {
      const statusResponse = await api.get("/billing/status");
      const invoicesResponse = await api.get("/billing/invoices?limit=10");
      
      setBillingStatus(statusResponse.data);
      setInvoices(invoicesResponse.data || []);
      setError(null);
    } catch (err: any) {
      console.error("Error fetching billing data:", err);
      setError(err.response?.data?.detail || "Failed to load billing information");
    } finally {
      setLoading(false);
    }
  };

  const handleUpgrade = async () => {
    try {
      // Redirect to pricing page
      window.location.href = "/pricing";
    } catch (err) {
      console.error("Error:", err);
    }
  };

  const handleCancelSubscription = async () => {
    try {
      setCanceling(true);
      await api.post("/billing/cancel-subscription", {
        at_period_end: true,
      });
      
      setShowCancelDialog(false);
      await fetchBillingData();
      
      // Show success notification
      setError(null);
    } catch (err: any) {
      console.error("Error canceling:", err);
      setError(err.response?.data?.detail || "Failed to cancel subscription");
    } finally {
      setCanceling(false);
    }
  };

  const handlePurchaseCredits = async () => {
    try {
      setCreditLoading(true);
      const response = await api.post("/billing/checkout/credits", {
        num_credits: creditAmount,
      });
      
      if (response.data.url) {
        window.location.href = response.data.url;
      }
    } catch (err: any) {
      console.error("Error purchasing credits:", err);
      setError(err.response?.data?.detail || "Failed to start checkout");
    } finally {
      setCreditLoading(false);
    }
  };

  if (loading) {
    return (
      <Container sx={{ display: "flex", justifyContent: "center", py: 6 }}>
        <CircularProgress />
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: "bold" }}>
          Billing & Subscription
        </Typography>
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setShowCreditDialog(true)}
          >
            Buy AI Credits
          </Button>
          <Button
            variant="outlined"
            onClick={handleUpgrade}
          >
            Upgrade Plan
          </Button>
        </Box>
      </Box>

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Tabs */}
      <Tabs value={tabValue} onChange={(_e, v) => setTabValue(v)} sx={{ mb: 3 }}>
        <Tab label="Overview" />
        <Tab label="Usage" />
        <Tab label="Invoices" />
        <Tab label="Payment Methods" />
      </Tabs>

      {/* TAB 0: OVERVIEW */}
      {tabValue === 0 && billingStatus && (
        <OverviewTab
          status={billingStatus}
          onCancel={() => setShowCancelDialog(true)}
        />
      )}

      {/* TAB 1: USAGE */}
      {tabValue === 1 && billingStatus && (
        <UsageTab status={billingStatus} />
      )}

      {/* TAB 2: INVOICES */}
      {tabValue === 2 && (
        <InvoicesTab invoices={invoices} />
      )}

      {/* TAB 3: PAYMENT METHODS */}
      {tabValue === 3 && (
        <PaymentMethodsTab />
      )}

      {/* Cancel Subscription Dialog */}
      <Dialog open={showCancelDialog} onClose={() => setShowCancelDialog(false)}>
        <DialogTitle>Cancel Subscription?</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Your subscription will be canceled at the end of current billing period.
            You'll lose access to paid features.
          </Alert>
          <Typography>
            We'd love to hear feedback about why you're canceling. Email us at support@hosprecruit.ai
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowCancelDialog(false)}>
            Keep Subscription
          </Button>
          <Button
            onClick={handleCancelSubscription}
            color="error"
            disabled={canceling}
          >
            {canceling ? "Canceling..." : "Cancel Subscription"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Purchase Credits Dialog */}
      <Dialog open={showCreditDialog} onClose={() => setShowCreditDialog(false)}>
        <DialogTitle>Purchase AI Credits</DialogTitle>
        <DialogContent sx={{ minWidth: 400, py: 2 }}>
          <Typography variant="body2" sx={{ mb: 2, color: "#666" }}>
            Each AI interview uses 1 credit. Unused credits roll over each month.
          </Typography>
          
          <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2, mb: 2 }}>
            {[50, 100, 250, 500].map((amount) => (
              <Button
                key={amount}
                variant={creditAmount === amount ? "contained" : "outlined"}
                onClick={() => setCreditAmount(amount)}
              >
                {amount} credits - ${(amount * 0.5).toFixed(2)}
              </Button>
            ))}
          </Box>

          <Box sx={{ p: 2, bgcolor: "#f5f5f5", borderRadius: 1 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
              <Typography variant="body2">Credits selected:</Typography>
              <Typography variant="body2" sx={{ fontWeight: "bold" }}>
                {creditAmount}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="h6">Total:</Typography>
              <Typography variant="h6" sx={{ fontWeight: "bold" }}>
                ${(creditAmount * 0.5).toFixed(2)}
              </Typography>
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowCreditDialog(false)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handlePurchaseCredits}
            disabled={creditLoading}
          >
            {creditLoading ? "Processing..." : "Purchase Credits"}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

// ============================================================================
// OVERVIEW TAB
// ============================================================================

const OverviewTab: React.FC<{
  status: BillingStatus;
  onCancel: () => void;
}> = ({ status, onCancel }) => {
  const isTrialing = status.subscription_status === "trialing";
  const isActive = status.subscription_status === "active";

  return (
    <Grid container spacing={3}>
      {/* Current Plan Card */}
      <Grid size={{ xs: 12, md: 6 }}>
        <Card>
          <CardHeader title="Current Plan" />
          <CardContent>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" sx={{ color: "#666" }}>
                Subscription Tier
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: "bold", mb: 1 }}>
                {status.tier_display}
              </Typography>
              
              <Chip
                label={status.subscription_status?.toUpperCase()}
                color={isActive ? "success" : isTrialing ? "info" : "default"}
                sx={{ mb: 2 }}
              />
            </Box>

            {/* Period */}
            {status.period_start && status.period_end && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: "#666" }}>
                  Billing Period
                </Typography>
                <Typography variant="body1">
                  {new Date(status.period_start).toLocaleDateString()} -{" "}
                  {new Date(status.period_end).toLocaleDateString()}
                </Typography>
              </Box>
            )}

            {/* Trial Info */}
            {isTrialing && status.trial.ends_at && (
              <Box sx={{ p: 2, bgcolor: "#e3f2fd", borderRadius: 1, mb: 2 }}>
                <Alert severity="info">
                  Trial ends on {new Date(status.trial.ends_at).toLocaleDateString()}.
                  Please add payment method to continue.
                </Alert>
              </Box>
            )}

            <Button variant="outlined" color="error" onClick={onCancel} startIcon={<CancelIcon />}>
              Cancel Subscription
            </Button>
          </CardContent>
        </Card>
      </Grid>

      {/* Quick Stats Card */}
      <Grid size={{ xs: 12, md: 6 }}>
        <Card>
          <CardHeader title="This Month" />
          <CardContent>
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Roles Posted</Typography>
                <Typography variant="body2">
                  {status.usage.roles_per_month.used}/{status.usage.roles_per_month.limit}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={(status.usage.roles_per_month.used / status.usage.roles_per_month.limit) * 100}
              />
            </Box>

            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Video Interviews Sent</Typography>
                <Typography variant="body2">
                  {status.usage.video_interviews_per_month.used}/{status.usage.video_interviews_per_month.limit}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={(status.usage.video_interviews_per_month.used / status.usage.video_interviews_per_month.limit) * 100}
              />
            </Box>

            <Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">AI Credits Used</Typography>
                <Typography variant="body2">
                  {status.usage.ai_credits_per_month.used}/{status.usage.ai_credits_per_month.limit}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={(status.usage.ai_credits_per_month.used / status.usage.ai_credits_per_month.limit) * 100}
              />
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};

// ============================================================================
// USAGE TAB
// ============================================================================

const UsageTab: React.FC<{ status: BillingStatus }> = ({ status }) => {
  const usageData = [
    {
      name: "Roles Posted",
      used: status.usage.roles_per_month.used,
      limit: status.usage.roles_per_month.limit,
      icon: "📋",
    },
    {
      name: "Video Interviews",
      used: status.usage.video_interviews_per_month.used,
      limit: status.usage.video_interviews_per_month.limit,
      icon: "🎥",
    },
    {
      name: "AI Credits",
      used: status.usage.ai_credits_per_month.used,
      limit: status.usage.ai_credits_per_month.limit,
      icon: "🤖",
    },
  ];

  return (
    <Grid container spacing={3}>
      {usageData.map((item) => (
        <Grid size={{ xs: 12, md: 4 }} key={item.name}>
          <Card>
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <Typography variant="h5">{item.icon}</Typography>
                <Typography variant="h6">{item.name}</Typography>
              </Box>

              <Box sx={{ mb: 1 }}>
                <LinearProgress
                  variant="determinate"
                  value={(item.used / item.limit) * 100}
                  sx={{ height: 10, borderRadius: 5 }}
                />
              </Box>

              <Box sx={{ display: "flex", justifyContent: "space-between" }}>
                <Typography variant="body2">${item.used.toLocaleString()}</Typography>
                <Typography variant="body2" sx={{ color: "#666" }}>
                  / {item.limit.toLocaleString()}
                </Typography>
              </Box>

              <Typography variant="caption" sx={{ color: "#999", display: "block", mt: 1 }}>
                {Math.round((item.used / item.limit) * 100)}% used
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
};

// ============================================================================
// INVOICES TAB
// ============================================================================

const InvoicesTab: React.FC<{ invoices: Invoice[] }> = ({ invoices }) => {
  if (invoices.length === 0) {
    return (
      <Card>
        <CardContent sx={{ textAlign: "center", py: 6 }}>
          <Typography sx={{ color: "#999" }}>
            No invoices yet. They'll appear here once you have an active subscription.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <TableContainer component={Card}>
      <Table>
        <TableHead>
          <TableRow sx={{ bgcolor: "#f5f5f5" }}>
            <TableCell sx={{ fontWeight: "bold" }}>Date</TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>Amount</TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>Status</TableCell>
            <TableCell sx={{ fontWeight: "bold" }} align="right">
              Action
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {invoices.map((invoice) => (
            <TableRow key={invoice.id}>
              <TableCell>
                {new Date(invoice.issue_date).toLocaleDateString()}
              </TableCell>
              <TableCell>
                ${(invoice.amount_total / 100).toFixed(2)} {invoice.currency.toUpperCase()}
              </TableCell>
              <TableCell>
                <Chip
                  label={invoice.status.toUpperCase()}
                  color={invoice.status === "paid" ? "success" : "default"}
                  size="small"
                />
              </TableCell>
              <TableCell align="right">
                <Button
                  size="small"
                  startIcon={<DownloadIcon />}
                  href={invoice.pdf_url || "#"}
                  disabled={!invoice.pdf_url}
                  download
                >
                  Download
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

// ============================================================================
// PAYMENT METHODS TAB
// ============================================================================

const PaymentMethodsTab: React.FC = () => {
  return (
    <Card>
      <CardHeader title="Payment Methods" />
      <CardContent>
        <Typography sx={{ mb: 2 }}>
          Manage your payment methods and billing information.
        </Typography>
        <Button variant="contained">
          Add Payment Method
        </Button>
      </CardContent>
    </Card>
  );
};

export default BillingDashboard;
