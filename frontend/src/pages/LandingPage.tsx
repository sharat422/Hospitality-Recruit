/**
 * Landing Page Component
 * Hero section with pain points, ROI metrics, and CTA
 */

import {
ArrowRight,
BarChart3,
Calendar,
Clock,
PhoneOff,
TrendingUp,
Zap
} from 'lucide-react';
import React,{ useState } from 'react';
import { Link } from 'react-router-dom';
import { DemoBookingModal } from '../components/DemoBookingModal';

export const LandingPage: React.FC = () => {
  const [isDemoModalOpen, setIsDemoModalOpen] = useState(false);

  return (
    <div className="min-h-screen bg-white">
      <DemoBookingModal isOpen={isDemoModalOpen} onClose={() => setIsDemoModalOpen(false)} />

      {/* Navigation */}
      <nav className="sticky top-0 z-40 bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center h-16">
          <div className="text-2xl font-bold text-purple-600">HospRecruit</div>
          <div className="flex items-center gap-3">
            <Link
              to="/auth"
              className="px-5 py-2 text-purple-600 border border-purple-600 rounded-lg hover:bg-purple-50 transition font-medium"
            >
              Login
            </Link>
            <button
              onClick={() => setIsDemoModalOpen(true)}
              className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition font-medium"
            >
              Get Free Audit
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-purple-50 via-white to-blue-50"></div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 sm:py-32">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Left: Copy */}
            <div className="space-y-8">
              {/* Badge */}
              <div className="inline-block">
                <span className="inline-flex items-center gap-2 px-4 py-2 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                  <Zap className="w-4 h-4" />
                  Hiring That Doesn't Suck
                </span>
              </div>

              {/* Headline */}
              <h1 className="text-5xl sm:text-6xl font-bold text-gray-900 leading-tight">
                Stop leaving{' '}
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-blue-600">
                  50% of your staff unfilled
                </span>
              </h1>

              {/* Subheadline */}
              <p className="text-xl text-gray-600 leading-relaxed">
                HospRecruit AI automates the entire hospitality hiring process. Screen 100+ candidates
                in minutes. Schedule shifts automatically. Fill roles 60% faster.
              </p>

              {/* CTA Buttons */}
              <div className="flex flex-col sm:flex-row gap-4 pt-4">
                <button
                  onClick={() => setIsDemoModalOpen(true)}
                  className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition font-semibold text-lg"
                >
                  <Calendar className="w-5 h-5" />
                  Get Free Audit →
                </button>
                <button className="inline-flex items-center justify-center px-8 py-4 border-2 border-gray-300 text-gray-900 rounded-lg hover:border-gray-400 transition font-semibold">
                  Watch Demo <ArrowRight className="w-5 h-5 ml-2" />
                </button>
              </div>

              {/* Trust badges */}
              <div className="pt-4 border-t border-gray-200">
                <p className="text-sm text-gray-600 mb-4 font-medium">
                  Trusted by 500+ hospitality teams
                </p>
                <div className="flex gap-4">
                  <img src="placeholder" alt="Client" className="h-8 w-auto" />
                  <img src="placeholder" alt="Client" className="h-8 w-auto" />
                  <img src="placeholder" alt="Client" className="h-8 w-auto" />
                </div>
              </div>
            </div>

            {/* Right: Visual */}
            <div className="relative hidden lg:block">
              <div className="absolute inset-0 bg-gradient-to-br from-purple-200 to-blue-200 rounded-2xl opacity-20 blur-3xl"></div>
              <div className="relative bg-gradient-to-br from-purple-600 to-blue-600 rounded-2xl p-8 text-white">
                <div className="space-y-4">
                  <div className="bg-white bg-opacity-10 rounded-lg p-4 backdrop-blur">
                    <p className="text-sm opacity-90">Applicants Screened (Today)</p>
                    <p className="text-3xl font-bold">247</p>
                  </div>
                  <div className="bg-white bg-opacity-10 rounded-lg p-4 backdrop-blur">
                    <p className="text-sm opacity-90">Positions Filled (This Month)</p>
                    <p className="text-3xl font-bold">18</p>
                  </div>
                  <div className="bg-white bg-opacity-10 rounded-lg p-4 backdrop-blur">
                    <p className="text-sm opacity-90">Time Saved</p>
                    <p className="text-3xl font-bold">31h</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Problem/Pain Points Section */}
      <section className="py-20 border-y border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-4xl font-bold text-gray-900 mb-4">The Hospitality Hiring Crisis</h2>
            <p className="text-xl text-gray-600">
              If this fits your team, you're losing $50k+ per bad hire
            </p>
          </div>

          {/* Pain Points Grid */}
          <div className="grid md:grid-cols-3 gap-6">
            {/* Problem 1 */}
            <div className="bg-red-50 border-l-4 border-red-500 p-6 rounded-lg">
              <div className="flex items-start gap-4">
                <Clock className="w-8 h-8 text-red-500 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Screening Takes Forever</h3>
                  <p className="text-gray-600">
                    Managers spend 30-40 hours/week reading resumes and rejecting 90% instantly.
                  </p>
                  <p className="text-sm text-red-600 font-semibold mt-3">
                    💀 $15k-25k wasted per hire
                  </p>
                </div>
              </div>
            </div>

            {/* Problem 2 */}
            <div className="bg-yellow-50 border-l-4 border-yellow-500 p-6 rounded-lg">
              <div className="flex items-start gap-4">
                <PhoneOff className="w-8 h-8 text-yellow-500 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">50% No-Show Rate</h3>
                  <p className="text-gray-600">
                    Candidates schedule interviews then don't show up. Shift workers ghost constantly.
                  </p>
                  <p className="text-sm text-yellow-600 font-semibold mt-3">
                    👻 60% more time to fill positions
                  </p>
                </div>
              </div>
            </div>

            {/* Problem 3 */}
            <div className="bg-orange-50 border-l-4 border-orange-500 p-6 rounded-lg">
              <div className="flex items-start gap-4">
                <Calendar className="w-8 h-8 text-orange-500 flex-shrink-0 mt-1" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Scheduling is a Nightmare</h3>
                  <p className="text-gray-600">
                    Spreadsheets and text chains. No one checks their availability before shifts.
                  </p>
                  <p className="text-sm text-orange-600 font-semibold mt-3">
                    🚨 30-50% daily unfilled shifts
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ROI Section */}
      <section className="py-20 bg-gradient-to-br from-purple-50 to-blue-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-4xl font-bold text-gray-900 mb-4">
              The HospRecruit AI Advantage
            </h2>
            <p className="text-xl text-gray-600">
              Real results from teams like yours
            </p>
          </div>

          {/* ROI Metrics Grid */}
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Metric 1 */}
            <div className="bg-white rounded-xl p-8 shadow-sm border border-gray-100 text-center">
              <div className="text-4xl font-bold text-purple-600 mb-2">70%</div>
              <p className="text-gray-600">Reduction in Screening Time</p>
              <p className="text-sm text-gray-500 mt-2">From 40 hours to 12 hours/week</p>
            </div>

            {/* Metric 2 */}
            <div className="bg-white rounded-xl p-8 shadow-sm border border-gray-100 text-center">
              <div className="text-4xl font-bold text-blue-600 mb-2">60%</div>
              <p className="text-gray-600">Faster Time-to-Hire</p>
              <p className="text-sm text-gray-500 mt-2">From 28 days to 11 days</p>
            </div>

            {/* Metric 3 */}
            <div className="bg-white rounded-xl p-8 shadow-sm border border-gray-100 text-center">
              <div className="text-4xl font-bold text-green-600 mb-2">50%</div>
              <p className="text-gray-600">Fewer No-Shows</p>
              <p className="text-sm text-gray-500 mt-2">Smart scheduling confirmation</p>
            </div>

            {/* Metric 4 */}
            <div className="bg-white rounded-xl p-8 shadow-sm border border-gray-100 text-center">
              <div className="text-4xl font-bold text-pink-600 mb-2">$1,080</div>
              <p className="text-gray-600">ROI Per Hire</p>
              <p className="text-sm text-gray-500 mt-2">Pays for itself in month 1</p>
            </div>
          </div>

          {/* Detailed Breakdown */}
          <div className="mt-16 bg-white rounded-xl p-8 border border-gray-200">
            <h3 className="text-2xl font-bold text-gray-900 mb-8 flex items-center gap-3">
              <BarChart3 className="w-6 h-6 text-purple-600" />
              How We Calculate Your ROI
            </h3>
            <div className="grid md:grid-cols-3 gap-8">
              <div>
                <p className="text-sm text-gray-600 font-medium mb-2">SCREENING SAVINGS</p>
                <p className="text-3xl font-bold text-gray-900">$12,000</p>
                <p className="text-sm text-gray-500">28 hours/month × $25/hour</p>
              </div>
              <div>
                <p className="text-sm text-gray-600 font-medium mb-2">FASTER HIRING BONUS</p>
                <p className="text-3xl font-bold text-gray-900">$3,500</p>
                <p className="text-sm text-gray-500">17 days saved × $200/day cost</p>
              </div>
              <div>
                <p className="text-sm text-gray-600 font-medium mb-2">NO-SHOW PREVENTION</p>
                <p className="text-3xl font-bold text-gray-900">$5,200</p>
                <p className="text-sm text-gray-500">2 filled shifts/day × $100 avg</p>
              </div>
            </div>
            <div className="mt-8 pt-8 border-t border-gray-200 flex justify-between items-center">
              <div>
                <p className="text-sm text-gray-600 font-medium">MONTHLY SAVINGS</p>
                <p className="text-4xl font-bold text-purple-600">$20,700</p>
              </div>
              <div>
                <p className="text-sm text-gray-600 font-medium mb-2">PLATFORM COST</p>
                <p className="text-2xl font-bold text-gray-900">$499/mo</p>
                <p className="text-sm text-green-600 font-semibold">Break-even: 2 weeks</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-4xl font-bold text-gray-900 mb-4">Everything You Need</h2>
            <p className="text-xl text-gray-600">Built specifically for hospitality teams</p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {/* Feature 1 */}
            <div className="p-6 border border-gray-200 rounded-xl hover:shadow-lg transition">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                <Zap className="w-6 h-6 text-purple-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">AI Screening</h3>
              <p className="text-gray-600">
                Auto-screen candidates based on top performer DNA. Surface hidden talent in seconds.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-6 border border-gray-200 rounded-xl hover:shadow-lg transition">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
                <Calendar className="w-6 h-6 text-blue-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Smart Scheduling</h3>
              <p className="text-gray-600">
                Automated shift scheduling with calendar sync. No more spreadsheets. Confirmation SMS.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-6 border border-gray-200 rounded-xl hover:shadow-lg transition">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-4">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">ATS Integration</h3>
              <p className="text-gray-600">
                Sync with 50+ ATS platforms. Real-time candidate updates. No duplicate entry.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-gradient-to-r from-purple-600 to-blue-600 text-white">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <h2 className="text-4xl font-bold">Ready to Fix Your Hiring?</h2>
          <p className="text-xl opacity-90">
            Get a free audit of your current process. Personalized ROI calculation. No credit card needed.
          </p>
          <button
            onClick={() => setIsDemoModalOpen(true)}
            className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-white text-purple-600 rounded-lg hover:bg-gray-100 transition font-semibold text-lg"
          >
            <Calendar className="w-5 h-5" />
            Schedule Your Free Audit Today
          </button>
          <p className="text-sm opacity-75">
            Takes 30 minutes. 500+ teams already benefiting.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center">
            <div className="text-white font-bold text-lg">HospRecruit</div>
            <div className="flex gap-6 text-sm">
              <a href="/terms" className="hover:text-white">Terms</a>
              <a href="/privacy" className="hover:text-white">Privacy</a>
              <a href="/contact" className="hover:text-white">Contact</a>
            </div>
          </div>
          <div className="mt-8 pt-8 border-t border-gray-800 text-center text-sm">
            <p>© 2026 HospRecruit AI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};
