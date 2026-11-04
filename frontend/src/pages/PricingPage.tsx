/**
React Pricing Page
Display pricing tiers and handle checkout
*/

import { apiClient as api } from '@/lib/api';
import {
Check as CheckIcon,
Close as CloseIcon
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
Grid,
Table,
TableBody,
TableCell,
TableContainer,
TableHead,
TableRow,
TextField,
Typography
} from '@mui/material';
import React,{ useEffect,useState } from 'react';

// ============================================================================
// PRICING DATA
// ============================================================================

const TIERS_DISPLAY = [
  {
    tier_name: "free_trial",
    display_name: "Free Trial",
    description: "14-day full access",
    price_monthly: 0,
    price_annual: 0,
    badge: "14 DAYS FREE",
    highlight: false,
  },
  {
    tier_name: "starter",
    display_name: "Starter",
    description: "Up to 25 roles/month",
    price_monthly: 149,
    price_annual: 1432,
    badge: null,
    highlight: false,
  },
  {
    tier_name: "growth",
    display_name: "Growth",
    description: "Up to 100 roles/month",
    price_monthly: 499,
    price_annual: 4790,
    badge: "RECOMMENDED",
    highlight: true,
  },
  {
    tier_name: "scale",
    display_name: "Scale",
    description: "Unlimited roles",
    price_monthly: 999,
    price_annual: 9590,
    badge: null,
    highlight: false,
  },
  {
    tier_name: "enterprise",
    display_name: "Enterprise",
    description: "Custom for your needs",
    price_monthly: null,
    price_annual: null,
    badge: "CONTACT US",
    highlight: false,
  },
];

const FEATURES_COMPARISON = [
  {
    name: "Roles per month",
    free_trial: "5",
    pilot: "10",
    starter: "25",
    growth: "100",
    scale: "500",
    enterprise: "Unlimited",
  },
  {
    name: "Video interviews per month",
    free_trial: "10",
    pilot: "25",
    starter: "50",
    growth: "250",
    scale: "1,000",
    enterprise: "Unlimited",
  },
  {
    name: "AI credits per month",
    free_trial: "20",
    pilot: "50",
    starter: "100",
    growth: "500",
    scale: "2,000",
    enterprise: "Unlimited",
  },
  {
    name: "AI Screening",
    free_trial: true,
    pilot: true,
    starter: true,
    growth: true,
    scale: true,
    enterprise: true,
  },
  {
    name: "SMS Screening",
    free_trial: true,
    pilot: true,
    starter: true,
    growth: true,
    scale: true,
    enterprise: true,
  },
  {
    name: "Interview Scheduling",
    free_trial: false,
    pilot: false,
    starter: true,
    growth: true,
    scale: true,
    enterprise: true,
  },
  {
    name: "Custom Branding",
    free_trial: false,
    pilot: false,
    starter: false,
    growth: true,
    scale: true,
    enterprise: true,
  },
  {
    name: "SSO & Advanced Security",
    free_trial: false,
    pilot: false,
    starter: false,
    growth: false,
    scale: true,
    enterprise: true,
  },
  {
    name: "API Access",
    free_trial: false,
    pilot: false,
    starter: false,
    growth: false,
    scale: true,
    enterprise: true,
  },
  {
    name: "Priority Support",
    free_trial: false,
    pilot: false,
    starter: false,
    growth: false,
    scale: false,
    enterprise: true,
  },
];

// ============================================================================
// PRICING PAGE COMPONENT
// ============================================================================

export const PricingPage: React.FC = () => {
  const [billingInterval, setBillingInterval] = useState<"month" | "year">("month");
  const [tiers, setTiers] = useState<Array<{ tier_name: string; display_name: string; description: string; price_monthly: number | null; price_annual: number | null; badge: string | null; highlight: boolean }>>(TIERS_DISPLAY);
  const [_loading, setLoading] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState("");
  
  
  const [error, setError] = useState<string | null>(null);
  const [success] = useState<string | null>(null);

  useEffect(() => {
    fetchPricingTiers();
  }, []);

  const fetchPricingTiers = async () => {
    try {
      setLoading(true);
      const { data } = await api.get<Array<{tier_name: string; price_monthly: number; price_annual: number}>>("/billing/pricing/tiers");
      setTiers(TIERS_DISPLAY.map(tier => ({ ...tier, ...data.find(item => item.tier_name === tier.tier_name) })));
      // Server tiers will override display tiers
      // For now, use display tiers with real pricing
    } catch (err) {
      console.error("Error fetching pricing:", err);
      setError("Failed to load pricing information");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckout = async (tierName: string) => {
    try {
      setCheckoutLoading(tierName);
      setError(null);

      const response = await api.post("/billing/checkout", {
        tier: tierName,
        billing_interval: billingInterval,
        promo_code: promoCode || undefined,
        return_url: window.location.origin,
      });

      if (response.data.url) {
        // Redirect to Stripe checkout
        window.location.href = response.data.url;
      } else {
        setError("Failed to create checkout session");
      }
    } catch (err: any) {
      console.error("Checkout error:", err);
      setError(err.response?.data?.detail || "Failed to start checkout");
    } finally {
      setCheckoutLoading(null);
    }
  };

  const discountedPrice = (price: number) => {
    return Math.round(price * 0.8); // 20% discount for annual
  };


  return (
    <div>
      {/* Header */}
      <Box sx={{ textAlign: "center", py: 6, bgcolor: "#f5f5f5" }}>
        <Container maxWidth="lg">
          <Typography variant="h3" sx={{ mb: 2, fontWeight: "bold" }}>
            Simple, Transparent Pricing
          </Typography>
          <Typography variant="h6" sx={{ color: "#666", mb: 4 }}>
            Choose the plan that scales with your recruitment needs
          </Typography>

          {/* Billing Toggle */}
          <Box sx={{ display: "flex", justifyContent: "center", gap: 2, mb: 4 }}>
            <Button
              variant={billingInterval === "month" ? "contained" : "outlined"}
              onClick={() => setBillingInterval("month")}
            >
              Monthly
            </Button>
            <Button
              variant={billingInterval === "year" ? "contained" : "outlined"}
              onClick={() => setBillingInterval("year")}
            >
              Annual <span style={{ marginLeft: "4px", color: "green" }}>−20%</span>
            </Button>
          </Box>

          {/* Promo Code Input */}
          <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mb: 4 }}>
            <TextField
              size="small"
              placeholder="Promo code"
              value={promoCode}
              onChange={(e) => setPromoCode(e.target.value)}
              sx={{ width: 150 }}
            />
            <Button variant="outlined">Apply Code</Button>
          </Box>

          {/* Trial & Pilot Offers */}
          <Box sx={{ display: "flex", gap: 2, justifyContent: "center", mb: 4 }}>
            <Alert severity="info">
              🎁 <strong>New customers:</strong> 14-day free trial, no credit card required
            </Alert>
            <Alert severity="success">
              💡 <strong>Pilot program:</strong> $99/month for first month
            </Alert>
          </Box>
        </Container>
      </Box>

      {/* Error/Success Messages */}
      {error && <Alert severity="error" sx={{ m: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ m: 2 }}>{success}</Alert>}

      {/* Pricing Cards */}
      <Container maxWidth="lg" sx={{ py: 6 }}>
        <Grid container spacing={3}>
          {tiers.map((tier) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={tier.tier_name}>
              <Card
                sx={{
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                  border: tier.highlight ? "3px solid #1976d2" : "1px solid #e0e0e0",
                  position: "relative",
                  transform: tier.highlight ? "scale(1.05)" : "scale(1)",
                  zIndex: tier.highlight ? 1 : 0,
                }}
              >
                {tier.badge && (
                  <Chip
                    label={tier.badge}
                    color={tier.badge === "RECOMMENDED" ? "primary" : "default"}
                    sx={{
                      position: "absolute",
                      top: -12,
                      left: 20,
                      fontWeight: "bold",
                    }}
                  />
                )}

                <CardHeader
                  title={tier.display_name}
                  subheader={tier.description}
                />

                <CardContent sx={{ flex: 1 }}>
                  {/* Pricing */}
                  <Box sx={{ mb: 3 }}>
                    {tier.price_monthly !== null ? (
                      <>
                        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
                          <Typography variant="h2" sx={{ fontWeight: "bold" }}>
                            ${billingInterval === "month"
                              ? tier.price_monthly
                              : discountedPrice(tier.price_annual ?? 0)}
                          </Typography>
                          <Typography variant="body1" sx={{ color: "#666" }}>
                            /{billingInterval === "month" ? "month" : "year"}
                          </Typography>
                        </Box>
                        {billingInterval === "year" && (
                          <Typography variant="caption" sx={{ color: "green", fontWeight: "bold" }}>
                            Save ${Math.round((tier.price_annual ?? 0) * 0.2 / 100 * 100) / 100}/year
                          </Typography>
                        )}
                      </>
                    ) : (
                      <Typography variant="h4" sx={{ fontWeight: "bold", color: "#1976d2" }}>
                        Custom pricing
                      </Typography>
                    )}
                  </Box>

                  {/* Features List */}
                  <Box sx={{ mb: 3 }}>
                    <FeaturesList tier={tier.tier_name} />
                  </Box>

                  {/* CTA Button */}
                  {tier.tier_name === "enterprise" ? (
                    <Button
                      fullWidth
                      variant="outlined"
                      href="mailto:sales@hosprecruit.ai"
                    >
                      Contact Sales
                    </Button>
                  ) : (
                    <Button
                      fullWidth
                      variant={tier.highlight ? "contained" : "outlined"}
                      onClick={() => handleCheckout(tier.tier_name)}
                      disabled={checkoutLoading === tier.tier_name}
                    >
                      {checkoutLoading === tier.tier_name ? (
                        <CircularProgress size={24} />
                      ) : tier.tier_name === "free_trial" ? (
                        "Start Free Trial"
                      ) : (
                        "Subscribe"
                      )}
                    </Button>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* Comparison Table */}
      <Container maxWidth="lg" sx={{ py: 6 }}>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: "bold" }}>
          Feature Comparison
        </Typography>

        <TableContainer>
          <Table>
            <TableHead>
              <TableRow sx={{ bgcolor: "#f5f5f5" }}>
                <TableCell sx={{ fontWeight: "bold" }}>Feature</TableCell>
                {["starter", "growth", "scale", "enterprise"].map((tier) => (
                  <TableCell key={tier} align="center" sx={{ fontWeight: "bold" }}>
                    {tier.charAt(0).toUpperCase() + tier.slice(1)}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {FEATURES_COMPARISON.map((feature) => (
                <TableRow key={feature.name}>
                  <TableCell sx={{ fontWeight: 500 }}>{feature.name}</TableCell>
                  {["starter", "growth", "scale", "enterprise"].map((tier) => (
                    <TableCell key={tier} align="center">
                      {typeof feature[tier as keyof typeof feature] === "boolean" ? (
                        feature[tier as keyof typeof feature] ? (
                          <CheckIcon sx={{ color: "green" }} />
                        ) : (
                          <CloseIcon sx={{ color: "#ccc" }} />
                        )
                      ) : (
                        <Typography variant="body2">
                          {feature[tier as keyof typeof feature]}
                        </Typography>
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Container>

      {/* FAQ Section */}
      <Container maxWidth="lg" sx={{ py: 6, bgcolor: "#f5f5f5" }}>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: "bold", textAlign: "center" }}>
          Frequently Asked Questions
        </Typography>

        <Grid container spacing={2}>
          {[
            {
              q: "Can I change my plan anytime?",
              a: "Yes, you can upgrade or downgrade at any time. Changes take effect at your next billing cycle.",
            },
            {
              q: "What payment methods do you accept?",
              a: "We accept all major credit and debit cards via Stripe.",
            },
            {
              q: "Is there a long-term contract?",
              a: "No contracts! You can cancel anytime with no setup fees.",
            },
            {
              q: "Do you offer discounts?",
              a: "Yes! Annual billing gives you 20% off. Contact us for volume discounts.",
            },
            {
              q: "What happens after my free trial?",
              a: "We'll email you before your trial ends. You can choose to upgrade or your account will be downgraded to free tier.",
            },
            {
              q: "Can I use credits instead of a subscription?",
              a: "Yes, purchase credits à la carte for video interviews at $0.50 per credit.",
            },
          ].map((faq, idx) => (
            <Grid size={{ xs: 12, sm: 6 }} key={idx}>
              <Box sx={{ mb: 2 }}>
                <Typography variant="h6" sx={{ fontWeight: "bold", mb: 1 }}>
                  {faq.q}
                </Typography>
                <Typography variant="body2" sx={{ color: "#666" }}>
                  {faq.a}
                </Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* CTA Section */}
      <Box sx={{ textAlign: "center", py: 6, bgcolor: "#1976d2", color: "white" }}>
        <Container maxWidth="lg">
          <Typography variant="h4" sx={{ mb: 2, fontWeight: "bold" }}>
            Ready to grow your recruitment?
          </Typography>
          <Typography variant="body1" sx={{ mb: 3 }}>
            Start your free 14-day trial today. No credit card required.
          </Typography>
          <Button
            variant="contained"
            size="large"
            sx={{
              bgcolor: "white",
              color: "#1976d2",
              fontWeight: "bold",
              "&:hover": { bgcolor: "#f0f0f0" },
            }}
            onClick={() => handleCheckout("free_trial")}
          >
            Start Free Trial
          </Button>
        </Container>
      </Box>
    </div>
  );
};

// ============================================================================
// HELPER COMPONENT: FEATURES LIST
// ============================================================================

const FeaturesList: React.FC<{ tier: string }> = ({ tier }) => {
  const features: Record<string, string[]> = {
    free_trial: [
      "5 roles/month",
      "10 video interviews/month",
      "20 AI credits",
      "AI screening included",
      "14-day access",
    ],
    pilot: [
      "10 roles/month",
      "25 video interviews/month",
      "50 AI credits",
      "AI screening included",
      "Interview scheduling",
    ],
    starter: [
      "25 roles/month",
      "50 video interviews/month",
      "100 AI credits included",
      "AI screening & SMS",
      "Interview scheduling",
    ],
    growth: [
      "100 roles/month",
      "250 video interviews/month",
      "500 AI credits included",
      "All features",
      "Custom branding",
      "Analytics dashboard",
    ],
    scale: [
      "500 roles/month",
      "1,000 video interviews/month",
      "2,000 AI credits included",
      "Everything in Growth",
      "SSO & advanced security",
      "API access",
    ],
    enterprise: [
      "Unlimited roles",
      "Unlimited video interviews",
      "Unlimited AI credits",
      "Full customization",
      "Dedicated support",
      "SLA guarantees",
    ],
  };

  return (
    <Box component="ul" sx={{ pl: 0, listStyle: "none" }}>
      {features[tier]?.map((feature) => (
        <Box
          component="li"
          key={feature}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            mb: 1,
            fontSize: "0.9rem",
          }}
        >
          <CheckIcon sx={{ width: 18, height: 18, color: "green", flexShrink: 0 }} />
          <span>{feature}</span>
        </Box>
      ))}
    </Box>
  );
};

export default PricingPage;
