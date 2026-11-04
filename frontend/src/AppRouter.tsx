/**
 * App Router Configuration
 * Defines all routes and layout
 */

import React from 'react';
import { Navigate,Route,BrowserRouter as Router,Routes } from 'react-router-dom';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthProvider } from './lib/AuthContext';

// Pages
import { AppLayout } from './components/AppLayout';
import { PropertyProvider } from './lib/PropertyContext';
import { RBACProvider } from './lib/RBACContext';
import AccommodationTransport from './pages/AccommodationTransport';
import AdminReferralDashboard from './pages/AdminReferralDashboard';
import AttendanceDashboard from './pages/AttendanceDashboard';
import { AuthCallbackPage } from './pages/AuthCallbackPage';
import { AuthPage } from './pages/AuthPage';
import { CandidatePipeline } from './pages/CandidatePipeline';
import CandidateScreening from './pages/CandidateScreening';
import CandidateStatusPortal from './pages/CandidateStatusPortal';
import CertificationManager from './pages/CertificationManager';
import DPDPPrivacyCenter from './pages/DPDPPrivacyCenter';
import { DashboardPage } from './pages/DashboardPage';
import DiversityDashboard from './pages/DiversityDashboard';
import DripSequenceBuilder from './pages/DripSequenceBuilder';
import Employee360 from './pages/Employee360';
import EmployeeApp from './pages/EmployeeApp';
import EmployeeEngagement from './pages/EmployeeEngagement';
import EmployeeExitManagement from './pages/EmployeeExitManagement';
import EmployeeLogin from './pages/EmployeeLogin';
import EmployeeRetention from './pages/EmployeeRetention';
import GhostingRiskDashboard from './pages/GhostingRiskDashboard';
import GrievanceManagement from './pages/GrievanceManagement';
import HospitalityAIAssistant from './pages/HospitalityAIAssistant';
import HotelManagement from './pages/HotelManagement';
import IndiaApplyForm from './pages/IndiaApplyForm';
import IndiaComplianceCenter from './pages/IndiaComplianceCenter';
import IndiaOnboarding from './pages/IndiaOnboarding';
import IndiaReferralProgram from './pages/IndiaReferralProgram';
import InterviewConfirmPage from './pages/InterviewConfirmPage';
import InterviewScheduler from './pages/InterviewScheduler';
import KYCManager from './pages/KYCManager';
import { LandingPage } from './pages/LandingPage';
import LearningCareer from './pages/LearningCareer';
import LeaveManagement from './pages/LeaveManagement';
import { MatchingDashboard } from './pages/MatchingDashboard';
import MessagingInbox from './pages/MessagingInbox';
import MobileApplicationForm from './pages/MobileApplicationForm';
import MobileFeatureHub from './pages/MobileFeatureHub';
import NPSDashboard from './pages/NPSDashboard';
import PayrollDashboard from './pages/PayrollDashboard';
import PerformanceManagement from './pages/PerformanceManagement';
import PMSIntegration from './pages/PMSIntegration';
import PrivacyCenter from './pages/PrivacyCenter';
import QRCodeManager from './pages/QRCodeManager';
import RTWUploadPortal from './pages/RTWUploadPortal';
import { ReactivationDashboard } from './pages/ReactivationDashboard';
import RecruitmentAnalytics from './pages/RecruitmentAnalytics';
import ReferralPortal from './pages/ReferralPortal';
import ReferralProgram from './pages/ReferralProgram';
import ReportingCenter from './pages/ReportingCenter';
import SalaryAdvanceManagement from './pages/SalaryAdvanceManagement';
import { SmartRecruitment } from './pages/SmartRecruitment';
import VideoRecorder from './pages/VideoRecorder';
import VideoReviewer from './pages/VideoReviewer';
import { WhatsAppBotDashboard } from './pages/WhatsAppBotDashboard';
import WorkforceAnalytics from './pages/WorkforceAnalytics';
import WorkforceScheduler from './pages/WorkforceScheduler';

export const AppRouter: React.FC = () => {
  return (
    <Router>
      <AuthProvider>
        <RBACProvider>
        <PropertyProvider>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route path="/employee-login" element={<EmployeeLogin />} />

          {/* Protected Routes */}
          <Route path="/employee-app" element={<ProtectedRoute permission="attendance.read"><EmployeeApp /></ProtectedRoute>} />
          <Route
            path="/employee-profile"
            element={
              <ProtectedRoute>
                <AppLayout><Employee360 /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/attendance"
            element={
              <ProtectedRoute permission="attendance.read">
                <AppLayout><AttendanceDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/shifts"
            element={
              <ProtectedRoute permission="attendance.read">
                <AppLayout><WorkforceScheduler /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route path="/leave" element={<ProtectedRoute permission="leave.read"><AppLayout><LeaveManagement /></AppLayout></ProtectedRoute>} />
          <Route path="/payroll" element={<ProtectedRoute permission="payroll.read"><AppLayout><PayrollDashboard /></AppLayout></ProtectedRoute>} />
          <Route
            path="/employees/:employeeId"
            element={
              <ProtectedRoute permission="employees.read">
                <AppLayout><Employee360 /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/pms"
            element={
              <ProtectedRoute permission="properties.read">
                <AppLayout><PMSIntegration /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/hotels"
            element={
              <ProtectedRoute permission="properties.read">
                <AppLayout><HotelManagement /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route path="/certifications" element={<ProtectedRoute permission="compliance.read"><AppLayout><CertificationManager /></AppLayout></ProtectedRoute>} />
          <Route path="/performance" element={<ProtectedRoute permission="performance.read"><AppLayout><PerformanceManagement /></AppLayout></ProtectedRoute>} />
          <Route path="/learning-career" element={<ProtectedRoute permission="training.read"><AppLayout><LearningCareer /></AppLayout></ProtectedRoute>} />
          <Route path="/employee-retention" element={<ProtectedRoute permission="employees.read"><AppLayout><EmployeeRetention /></AppLayout></ProtectedRoute>} />
          <Route path="/employee-engagement" element={<ProtectedRoute permission="employees.read"><AppLayout><EmployeeEngagement /></AppLayout></ProtectedRoute>} />
          <Route path="/employee-exit" element={<ProtectedRoute permission="employees.read"><AppLayout><EmployeeExitManagement /></AppLayout></ProtectedRoute>} />
          <Route path="/grievances" element={<ProtectedRoute permission="complaints.read"><AppLayout><GrievanceManagement /></AppLayout></ProtectedRoute>} />
          <Route path="/salary-advances" element={<ProtectedRoute permission="payroll.read"><AppLayout><SalaryAdvanceManagement /></AppLayout></ProtectedRoute>} />
          <Route path="/facilities" element={<ProtectedRoute permission="employees.read"><AppLayout><AccommodationTransport /></AppLayout></ProtectedRoute>} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute permission="reports.read">
                <AppLayout><DashboardPage /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route path="/analytics" element={<ProtectedRoute permission="reports.read"><AppLayout><RecruitmentAnalytics /></AppLayout></ProtectedRoute>} />
          <Route path="/workforce-analytics" element={<ProtectedRoute permission="employees.read"><AppLayout><WorkforceAnalytics /></AppLayout></ProtectedRoute>} />
          <Route path="/reports" element={<ProtectedRoute permission="reports.read"><AppLayout><ReportingCenter /></AppLayout></ProtectedRoute>} />
          <Route path="/ai-assistant" element={<ProtectedRoute permission="reports.read"><AppLayout><HospitalityAIAssistant /></AppLayout></ProtectedRoute>} />
          <Route
            path="/matching"
            element={
              <ProtectedRoute permission="candidates.read">
                <AppLayout><MatchingDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/pipeline"
            element={
              <ProtectedRoute permission="candidates.read">
                <AppLayout><CandidatePipeline /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/reactivation"
            element={
              <ProtectedRoute permission="candidates.read">
                <AppLayout><ReactivationDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/messaging"
            element={
              <ProtectedRoute permission="candidates.read">
                <AppLayout><MessagingInbox /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ghosting-risk"
            element={
              <ProtectedRoute permission="candidates.read">
                <AppLayout><GhostingRiskDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/interviews"
            element={
              <ProtectedRoute permission="applications.manage">
                <AppLayout><InterviewScheduler /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/drip"
            element={
              <ProtectedRoute permission="applications.manage">
                <AppLayout><DripSequenceBuilder /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/nps"
            element={
              <ProtectedRoute permission="reports.read">
                <AppLayout><NPSDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />

          {/* Feature 04 — Protected routes */}
          <Route
            path="/video-review/:interviewId"
            element={
              <ProtectedRoute permission="applications.read">
                <VideoReviewer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/qr-codes"
            element={
              <ProtectedRoute permission="jobs.manage">
                <QRCodeManager />
              </ProtectedRoute>
            }
          />
          <Route
            path="/mobile-features"
            element={
              <ProtectedRoute permission="jobs.read">
                <MobileFeatureHub />
              </ProtectedRoute>
            }
          />

          {/* Feature 06 India — India Compliance (replaces Western RTW/GDPR/EEO) */}
          <Route
            path="/india-compliance"
            element={
              <ProtectedRoute permission="compliance.read">
                <AppLayout><IndiaComplianceCenter /></AppLayout>
              </ProtectedRoute>
            }
          />
          {/* Legacy Western routes kept for redirect safety — now point to India compliance */}
          <Route path="/rtw"        element={<Navigate to="/india-compliance" replace />} />
          <Route path="/compliance" element={<Navigate to="/india-compliance" replace />} />
          <Route path="/privacy"    element={<Navigate to="/india-compliance" replace />} />
          <Route path="/dei"        element={<Navigate to="/india-compliance" replace />} />
          <Route
            path="/referrals"
            element={
              <ProtectedRoute>
                <AppLayout><ReferralProgram /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/india-referrals"
            element={
              <ProtectedRoute>
                <AppLayout><IndiaReferralProgram /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/referral-portal"
            element={
              <ProtectedRoute>
                <AppLayout><ReferralPortal /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin-referrals"
            element={
              <ProtectedRoute permission="financial.read">
                <AppLayout><AdminReferralDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/diversity"
            element={
              <ProtectedRoute permission="reports.read">
                <AppLayout><DiversityDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/kyc"
            element={
              <ProtectedRoute permission="compliance.read">
                <AppLayout><KYCManager /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/dpdp-admin"
            element={
              <ProtectedRoute permission="compliance.manage">
                <AppLayout><DPDPPrivacyCenter /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/smart-recruitment"
            element={
              <ProtectedRoute permission="jobs.manage">
                <AppLayout><SmartRecruitment /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/whatsapp-bot"
            element={
              <ProtectedRoute permission="employees.read">
                <AppLayout><WhatsAppBotDashboard /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/screening"
            element={
              <ProtectedRoute permission="candidates.read">
                <AppLayout><CandidateScreening /></AppLayout>
              </ProtectedRoute>
            }
          />

          <Route
            path="/india-onboarding"
            element={
              <ProtectedRoute permission="employees.manage">
                <AppLayout><IndiaOnboarding /></AppLayout>
              </ProtectedRoute>
            }
          />

          {/* Public — India apply form (no auth) */}
          <Route path="/india-apply/:jobId" element={<IndiaApplyForm />} />

          {/* Public — no auth, no AppLayout */}
          <Route path="/privacy-centre/:token" element={<PrivacyCenter />} />
          <Route path="/rtw-upload/:token" element={<RTWUploadPortal />} />
          <Route path="/track/:token" element={<CandidateStatusPortal />} />
          <Route path="/schedule/:token" element={<InterviewConfirmPage />} />
          <Route path="/apply/:jobRoleId" element={<MobileApplicationForm />} />
          <Route path="/video-interview/:token" element={<VideoRecorder />} />

          {/* Catch all - redirect to home */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </PropertyProvider>
        </RBACProvider>
      </AuthProvider>
    </Router>
  );
};
