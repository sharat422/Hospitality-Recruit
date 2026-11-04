/**
 * Demo Booking Form Component
 * Captures lead information and triggers email notifications
 */

import { AlertCircle,Calendar,Loader,Users,X } from 'lucide-react';
import React,{ useState } from 'react';
import { useAuth } from '../lib/AuthContext';
import { apiCall } from '../lib/auth';

interface DemoBookingProps {
  isOpen: boolean;
  onClose: () => void;
  demoType?: 'general' | 'screening' | 'scheduling';
  prefilledEmail?: string;
}

const PAIN_POINTS = [
  '❌ Time-consuming manual screening',
  '📞 High no-show rates on interviews',
  '⏰ Difficulty scheduling shifts',
  '💰 High turnover costs',
  '📊 Lack of hiring visibility',
  '🔄 Poor candidate experience',
];

const COMPANY_SIZES = ['1-50', '50-200', '200-500', '500+'];
const HIRING_VOLUMES = ['1-5', '5-10', '10-50', '50+'];
const BUDGET_RANGES = ['Under $500', '$500-$2k', '$2k-$5k', '$5k+'];

export const DemoBookingModal: React.FC<DemoBookingProps> = ({
  isOpen,
  onClose,
  demoType = 'general',
  prefilledEmail = '',
}) => {
  const { user } = useAuth();
  const [step, setStep] = useState<'contact' | 'details' | 'painpoints' | 'success'>(
    'contact'
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    first_name: user?.user_metadata?.first_name || '',
    last_name: user?.user_metadata?.last_name || '',
    email: user?.email || prefilledEmail || '',
    company_name: user?.user_metadata?.company_name || '',
    phone: '',
    hiring_volume: '',
    company_size: '',
    budget_range: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    current_pain_points: [] as string[],
    notes: '',
    demo_type: demoType,
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handlePainPointToggle = (painPoint: string) => {
    setFormData((prev) => ({
      ...prev,
      current_pain_points: prev.current_pain_points.includes(painPoint)
        ? prev.current_pain_points.filter((p) => p !== painPoint)
        : [...prev.current_pain_points, painPoint],
    }));
  };

  const handleSelectChange = (
    e: React.ChangeEvent<HTMLSelectElement>,
    field: keyof typeof formData
  ) => {
    setFormData((prev) => ({
      ...prev,
      [field]: e.target.value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await apiCall('/demo/request', { method: 'POST', body: JSON.stringify({ ...formData, demo_type: demoType }) });
      setStep('success');

      // Reset form after 5 seconds
      setTimeout(() => {
        setStep('contact');
        setFormData({
          first_name: user?.user_metadata?.first_name || '',
          last_name: user?.user_metadata?.last_name || '',
          email: user?.email || '',
          company_name: user?.user_metadata?.company_name || '',
          phone: '',
          hiring_volume: '',
          company_size: '',
          budget_range: '',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          current_pain_points: [],
          notes: '',
          demo_type: demoType,
        });
        onClose();
      }, 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to book demo');
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-gradient-to-r from-purple-600 to-purple-700 text-white px-6 py-4 flex justify-between items-center border-b">
          <h2 className="text-xl font-bold">
            {step === 'success' ? '🎉 Demo Booked!' : 'Schedule Your Free Demo'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-purple-500 rounded transition"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {step === 'success' ? (
            <div className="text-center space-y-4">
              <div className="text-5xl">🚀</div>
              <h3 className="text-2xl font-bold text-gray-900">Awesome!</h3>
              <p className="text-gray-600">
                We've received your demo request. Our team will reach out within 24 hours to
                confirm the time and answer any questions.
              </p>
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-left">
                <p className="font-semibold text-gray-900 mb-2">What happens next:</p>
                <ul className="space-y-1 text-sm text-gray-600">
                  <li>✓ Confirmation email sent to {formData.email}</li>
                  <li>✓ Calendar invite with video call link</li>
                  <li>✓ Pre-demo audit of your process</li>
                  <li>✓ Custom ROI calculation</li>
                </ul>
              </div>
              <p className="text-xs text-gray-500">
                This window will close automatically. You can also access your demo details in
                your account dashboard.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Step 1: Contact */}
              {(step === 'contact' || step === 'details') && (
                <>
                  <div className="border-b pb-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <span className="flex items-center justify-center w-8 h-8 bg-purple-100 text-purple-600 rounded-full text-sm font-bold">
                        1
                      </span>
                      Your Information
                    </h3>
                    <div className="grid grid-cols-2 gap-4">
                      <input
                        type="text"
                        name="first_name"
                        placeholder="First Name"
                        value={formData.first_name}
                        onChange={handleInputChange}
                        required
                        className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <input
                        type="text"
                        name="last_name"
                        placeholder="Last Name"
                        value={formData.last_name}
                        onChange={handleInputChange}
                        required
                        className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <input
                        type="email"
                        name="email"
                        placeholder="Email"
                        value={formData.email}
                        onChange={handleInputChange}
                        required
                        className="col-span-2 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <input
                        type="tel"
                        name="phone"
                        placeholder="Phone (optional)"
                        value={formData.phone}
                        onChange={handleInputChange}
                        className="col-span-2 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <input
                        type="text"
                        name="company_name"
                        placeholder="Company Name"
                        value={formData.company_name}
                        onChange={handleInputChange}
                        required
                        className="col-span-2 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                    </div>
                  </div>
                </>
              )}

              {/* Step 2: Details */}
              {(step === 'details' || step === 'painpoints') && (
                <>
                  <div className="border-b pb-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <Users className="w-5 h-5 text-purple-600" />
                      <span className="flex items-center justify-center w-8 h-8 bg-purple-100 text-purple-600 rounded-full text-sm font-bold">
                        2
                      </span>
                      Company Details
                    </h3>
                    <div className="space-y-4">
                      <select
                        value={formData.company_size}
                        onChange={(e) => handleSelectChange(e, 'company_size')}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      >
                        <option value="">Select Company Size</option>
                        {COMPANY_SIZES.map((size) => (
                          <option key={size} value={size}>
                            {size} employees
                          </option>
                        ))}
                      </select>

                      <select
                        value={formData.hiring_volume}
                        onChange={(e) => handleSelectChange(e, 'hiring_volume')}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      >
                        <option value="">Monthly Hiring Volume</option>
                        {HIRING_VOLUMES.map((volume) => (
                          <option key={volume} value={volume}>
                            {volume} roles/month
                          </option>
                        ))}
                      </select>

                      <select
                        value={formData.budget_range}
                        onChange={(e) => handleSelectChange(e, 'budget_range')}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      >
                        <option value="">Monthly Budget Range</option>
                        {BUDGET_RANGES.map((budget) => (
                          <option key={budget} value={budget}>
                            {budget}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="border-b pb-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <AlertCircle className="w-5 h-5 text-purple-600" />
                      <span className="flex items-center justify-center w-8 h-8 bg-purple-100 text-purple-600 rounded-full text-sm font-bold">
                        3
                      </span>
                      Pain Points (Select All That Apply)
                    </h3>
                    <div className="space-y-2">
                      {PAIN_POINTS.map((point) => (
                        <label key={point} className="flex items-center gap-3 cursor-pointer p-2 hover:bg-gray-50 rounded">
                          <input
                            type="checkbox"
                            checked={formData.current_pain_points.includes(point)}
                            onChange={() => handlePainPointToggle(point)}
                            className="w-5 h-5 text-purple-600 rounded focus:ring-purple-500"
                          />
                          <span className="text-gray-700">{point}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Additional Notes (Optional)
                    </label>
                    <textarea
                      name="notes"
                      placeholder="Tell us about your specific needs..."
                      value={formData.notes}
                      onChange={handleInputChange}
                      rows={3}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                </>
              )}

              {/* Error */}
              {error && (
                <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
                  ✗ {error}
                </div>
              )}

              {/* Navigation */}
              <div className="flex gap-3">
                {step === 'painpoints' && (
                  <button
                    type="button"
                    onClick={() => setStep('details')}
                    className="flex-1 px-4 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition"
                  >
                    Back
                  </button>
                )}

                {step === 'contact' ? (
                  <button
                    type="button"
                    onClick={() => setStep('details')}
                    className="flex-1 bg-purple-600 text-white py-3 rounded-lg hover:bg-purple-700 font-medium transition"
                  >
                    Next
                  </button>
                ) : step === 'details' ? (
                  <button
                    type="button"
                    onClick={() => setStep('painpoints')}
                    className="flex-1 bg-purple-600 text-white py-3 rounded-lg hover:bg-purple-700 font-medium transition"
                  >
                    Next
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="flex-1 bg-purple-600 text-white py-3 rounded-lg hover:bg-purple-700 disabled:opacity-50 font-medium transition flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <>
                        <Loader className="w-5 h-5 animate-spin" />
                        Booking...
                      </>
                    ) : (
                      <>
                        <Calendar className="w-5 h-5" />
                        Schedule Demo
                      </>
                    )}
                  </button>
                )}
              </div>

              {/* Progress */}
              <div className="flex gap-1">
                {['contact', 'details', 'painpoints'].map((s) => (
                  <div
                    key={s}
                    className={`h-1 flex-1 rounded-full transition ${
                      ['contact', 'details', 'painpoints'].indexOf(step) >=
                      ['contact', 'details', 'painpoints'].indexOf(s as any)
                        ? 'bg-purple-600'
                        : 'bg-gray-200'
                    }`}
                  />
                ))}
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
