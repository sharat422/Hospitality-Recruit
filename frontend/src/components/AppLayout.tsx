import {
AlertTriangle,
Award,
BarChart2,
Bot,
Briefcase,
Building2,
CalendarDays,
ChevronDown,
ChevronRight,
ClipboardCheck,
ClipboardCheck as ClipboardCheckIcon,
Clock3,
CreditCard,
Equal,
FileText,
Gift,
GraduationCap,
LayoutDashboard,
List,
Lock,
LogOut,
Menu,
MessageSquare,
QrCode,
RefreshCcw,
ScanSearch,
Search,
Shield,
ShieldCheck,
Smartphone,
Star,
UserCheck,
Users,
Video,
Plug,
Wand2,
X,
Zap
} from 'lucide-react'
import React,{ useState } from 'react'
import { Link,useLocation,useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import { useProperty } from '../lib/PropertyContext'
import { useRBAC } from '../lib/RBACContext'
import { signOut } from '../lib/auth'
import { GlobalSearch } from './GlobalSearch'

interface NavItem {
  label: string
  to: string
  icon: React.ReactNode
}

const ROUTE_PERMISSIONS: Record<string, string> = {
  '/dashboard': 'reports.read', '/hotels': 'properties.read', '/pms': 'properties.read', '/matching': 'candidates.read',
  '/pipeline': 'candidates.read', '/reactivation': 'candidates.read', '/messaging': 'candidates.read',
  '/ghosting-risk': 'candidates.read', '/interviews': 'applications.manage', '/drip': 'applications.manage',
  '/nps': 'reports.read', '/candidates': 'candidates.read', '/shifts': 'attendance.read',
  '/onboarding': 'employees.manage', '/analytics': 'reports.read', '/workforce-analytics': 'employees.read', '/reports': 'reports.read', '/talent-pool': 'candidates.read',
  '/qr-codes': 'jobs.manage', '/video-review/new': 'applications.read',
  '/mobile-features': 'jobs.read', '/kyc': 'compliance.read', '/india-compliance': 'compliance.read',
  '/dpdp-admin': 'compliance.manage', '/diversity': 'reports.read', '/admin-referrals': 'financial.read',
  '/smart-recruitment': 'jobs.manage', '/whatsapp-bot': 'employees.read', '/screening': 'candidates.read',
  '/india-onboarding': 'employees.manage',
  '/employees': 'employees.read',
  '/attendance': 'attendance.read',
  '/leave': 'leave.read',
  '/payroll': 'payroll.read',
  '/employee-app': 'attendance.read',
  '/certifications': 'compliance.read',
  '/performance': 'performance.read',
  '/learning-career': 'training.read',
  '/employee-retention': 'employees.read',
  '/employee-engagement': 'employees.read',
  '/employee-exit': 'employees.read',
  '/grievances': 'complaints.read',
  '/salary-advances': 'payroll.read',
  '/facilities': 'employees.read',
  '/ai-assistant': 'reports.read',
}

interface NavGroup {
  label: string
  icon: React.ReactNode
  items: NavItem[]
}

const NAV_LINKS: NavItem[] = [
  { label: 'Dashboard', to: '/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
  { label: 'Hotels & Properties', to: '/hotels', icon: <Building2 className="w-4 h-4" /> },
  { label: 'PMS & Staffing Demand', to: '/pms', icon: <Plug className="w-4 h-4" /> },
  { label: 'My Employee Profile', to: '/employee-profile', icon: <UserCheck className="w-4 h-4" /> },
  { label: 'Employee App', to: '/employee-app', icon: <Smartphone className="w-4 h-4" /> },
  { label: 'Attendance', to: '/attendance', icon: <Clock3 className="w-4 h-4" /> },
  { label: 'Leave', to: '/leave', icon: <CalendarDays className="w-4 h-4" /> },
  { label: 'Payroll', to: '/payroll', icon: <CreditCard className="w-4 h-4" /> },
  { label: 'Salary Advances', to: '/salary-advances', icon: <CreditCard className="w-4 h-4" /> },
  { label: 'Accommodation & Transport', to: '/facilities', icon: <Building2 className="w-4 h-4" /> },
  { label: 'Certifications', to: '/certifications', icon: <Award className="w-4 h-4" /> },
  { label: 'Performance', to: '/performance', icon: <Star className="w-4 h-4" /> },
  { label: 'Learning & Career', to: '/learning-career', icon: <GraduationCap className="w-4 h-4" /> },
  { label: 'Employee Retention', to: '/employee-retention', icon: <AlertTriangle className="w-4 h-4" /> },
  { label: 'Employee Engagement', to: '/employee-engagement', icon: <Star className="w-4 h-4" /> },
  { label: 'Employee Exit', to: '/employee-exit', icon: <LogOut className="w-4 h-4" /> },
  { label: 'Grievances & POSH', to: '/grievances', icon: <ShieldCheck className="w-4 h-4" /> },
]

const FEATURE_GROUPS: NavGroup[] = [
  {
    label: 'Features',
    icon: <Zap className="w-4 h-4" />,
    items: [
      // AI Screening & Matching
      { label: 'Resume Parsing',        to: '/matching?tab=resume',       icon: <FileText className="w-4 h-4" /> },
      { label: 'Rank Candidates',       to: '/matching?tab=rank',         icon: <List className="w-4 h-4" /> },
      { label: 'JD Generator',          to: '/matching?tab=jd',           icon: <Wand2 className="w-4 h-4" /> },
      { label: 'Talent Reactivation',   to: '/matching?tab=reactivation', icon: <RefreshCcw className="w-4 h-4" /> },
      { label: 'Passive Discovery',     to: '/matching?tab=passive',      icon: <UserCheck className="w-4 h-4" /> },
      { label: 'Skill Taxonomy',        to: '/matching?tab=taxonomy',     icon: <Search className="w-4 h-4" /> },
      { label: 'Candidate Pipeline',    to: '/pipeline',                  icon: <Users className="w-4 h-4" /> },
      { label: 'Reactivation Dashboard', to: '/reactivation',             icon: <RefreshCcw className="w-4 h-4" /> },
      // Anti-Ghosting & Engagement (Feature 02)
      { label: 'Messaging Inbox',       to: '/messaging',                 icon: <MessageSquare className="w-4 h-4" /> },
      { label: 'Ghosting Risk',         to: '/ghosting-risk',             icon: <AlertTriangle className="w-4 h-4" /> },
      { label: 'Interview Scheduler',   to: '/interviews',                icon: <CalendarDays className="w-4 h-4" /> },
      { label: 'Drip Sequences',        to: '/drip',                      icon: <Zap className="w-4 h-4" /> },
      { label: 'NPS Dashboard',         to: '/nps',                       icon: <BarChart2 className="w-4 h-4" /> },
      // Core modules
      { label: 'Candidates',            to: '/candidates',                icon: <Users className="w-4 h-4" /> },
      { label: 'Shift Scheduling',      to: '/shifts',                    icon: <CalendarDays className="w-4 h-4" /> },
      { label: 'SMS Recruiting',        to: '/sms',                       icon: <MessageSquare className="w-4 h-4" /> },
      { label: 'Onboarding',            to: '/onboarding',                icon: <ClipboardCheck className="w-4 h-4" /> },
      { label: 'Analytics',             to: '/analytics',                 icon: <BarChart2 className="w-4 h-4" /> },
      { label: 'Workforce Analytics',   to: '/workforce-analytics',       icon: <BarChart2 className="w-4 h-4" /> },
      { label: 'Reporting Center',      to: '/reports',                   icon: <FileText className="w-4 h-4" /> },
      { label: 'AI Assistant',          to: '/ai-assistant',              icon: <Bot className="w-4 h-4" /> },
      { label: 'Talent Pool',           to: '/talent-pool',               icon: <Star className="w-4 h-4" /> },
      // Mobile Experience (Feature 04)
      { label: 'QR Codes',              to: '/qr-codes',                  icon: <QrCode className="w-4 h-4" /> },
      { label: 'Video Reviews',         to: '/video-review/new',          icon: <Video className="w-4 h-4" /> },
      { label: 'Mobile Features',       to: '/mobile-features',           icon: <Smartphone className="w-4 h-4" /> },
      // Feature 06 — India Compliance
      { label: 'KYC Manager 🪪',         to: '/kyc',                       icon: <ShieldCheck className="w-4 h-4" /> },
      { label: 'India Compliance 🇮🇳',  to: '/india-compliance',          icon: <Shield className="w-4 h-4" /> },
      { label: 'DPDP Privacy 🔏',        to: '/dpdp-admin',                icon: <Lock className="w-4 h-4" /> },
      { label: 'Diversity 🏳️',          to: '/diversity',                 icon: <Equal className="w-4 h-4" /> },
      { label: 'Referral Program',      to: '/referrals',                 icon: <Gift className="w-4 h-4" /> },
      { label: 'India Referrals 🇮🇳',  to: '/india-referrals',           icon: <Gift className="w-4 h-4" /> },
      { label: 'Referral Portal 📱',   to: '/referral-portal',           icon: <Smartphone className="w-4 h-4" /> },
      { label: 'Admin Referrals 🛠️',  to: '/admin-referrals',           icon: <Shield className="w-4 h-4" /> },
      // WhatsApp HR Bot
      { label: 'Smart Recruitment 🏨',  to: '/smart-recruitment',         icon: <Briefcase className="w-4 h-4" /> },
      { label: 'WhatsApp Bot 🤖',       to: '/whatsapp-bot',              icon: <Bot className="w-4 h-4" /> },
      { label: 'AI Screening 🧠',       to: '/screening',                 icon: <ScanSearch className="w-4 h-4" /> },
      { label: 'Digital Onboarding 📋', to: '/india-onboarding',          icon: <ClipboardCheckIcon className="w-4 h-4" /> },
    ],
  },
]

function Sidebar({ onClose }: { onClose?: () => void }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { properties, activeProperty, loading: propertiesLoading, switchProperty } = useProperty()
  const { can, profile } = useRBAC()
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({ Features: true })

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  const isActive = (to: string) => {
    const path = to.split('?')[0]
    return location.pathname === path
  }

  return (
    <div className="flex flex-col h-full bg-white border-r border-gray-200 w-64">
      {/* Logo */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <Link to="/dashboard" className="text-xl font-bold text-purple-600">
          HospRecruit
        </Link>
        {onClose && (
          <button onClick={onClose} className="sm:hidden p-1 rounded hover:bg-gray-100">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Nav */}
      <div className="border-b border-gray-200 px-3 py-3">
        <label className="mb-1 block px-1 text-xs font-medium text-gray-500">Active property</label>
        <select
          value={activeProperty?.id ?? ''}
          disabled={propertiesLoading || properties.length === 0}
          onChange={(event) => void switchProperty(event.target.value)}
          className="min-h-10 w-full rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-700 focus:border-purple-500 focus:outline-none"
          aria-label="Switch active property"
        >
          {properties.length === 0 && <option value="">No properties assigned</option>}
          {properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}
        </select>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {/* Top-level links */}
        {NAV_LINKS.filter(item => !ROUTE_PERMISSIONS[item.to] || can(ROUTE_PERMISSIONS[item.to])).map((item) => (
          <Link
            key={item.to}
            to={item.to}
            onClick={onClose}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition ${
              isActive(item.to)
                ? 'bg-purple-50 text-purple-700'
                : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            {item.icon}
            {item.label}
          </Link>
        ))}

        {/* Feature groups */}
        {FEATURE_GROUPS.map((group) => (
          <div key={group.label}>
            <button
              onClick={() =>
                setOpenGroups((prev) => ({ ...prev, [group.label]: !prev[group.label] }))
              }
              className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 transition"
            >
              <span className="flex items-center gap-3">
                {group.icon}
                {group.label}
              </span>
              {openGroups[group.label] ? (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-400" />
              )}
            </button>

            {openGroups[group.label] && (
              <div className="mt-1 ml-4 space-y-1 border-l border-gray-200 pl-3">
                {group.items.filter(item => {
                  const path = item.to.split('?')[0]
                  const permission = ROUTE_PERMISSIONS[path]
                  return !permission || can(permission)
                }).map((item) => (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={onClose}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition ${
                      location.search.includes(item.to.split('?')[1] ?? '') &&
                      isActive(item.to)
                        ? 'bg-purple-50 text-purple-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {item.icon}
                    {item.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* User + sign out */}
      <div className="border-t border-gray-200 px-4 py-4">
        <p className="text-xs text-gray-500 truncate">{user?.email}</p>
        <p className="mb-3 mt-1 text-xs font-medium text-purple-700">{profile?.role?.replaceAll('_', ' ')}</p>
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
      </div>
    </div>
  )
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden sm:flex flex-shrink-0">
        <Sidebar />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-50 flex sm:hidden">
          <div
            className="absolute inset-0 bg-black bg-opacity-40"
            onClick={() => setMobileSidebarOpen(false)}
          />
          <div className="relative z-10">
            <Sidebar onClose={() => setMobileSidebarOpen(false)} />
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Shared application header */}
        <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-3 py-3 sm:px-6">
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="rounded p-1 hover:bg-gray-100 sm:hidden"
            aria-label="Open navigation"
          >
            <Menu className="w-6 h-6" />
          </button>
          <GlobalSearch />
        </div>

        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  )
}
