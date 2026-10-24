import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { apiClient } from '../../services/apiClient';

interface HumanInTheLoopProtocolProps {
  onApproval: (action: string) => void;
  onCancel: () => void;
  actionDetails: Record<string, unknown>;
}

interface ActionDetails {
  description?: string;
  type?: string;
  impact?: string;
  priority?: string;
  requiresOtp?: boolean;
  actionId: string;
}

interface AuditEntry {
  step: number;
  status: string;
  timestamp: string;
  actor: string;
  action: string;
}

const HumanInTheLoopProtocol: React.FC<HumanInTheLoopProtocolProps> = ({ onApproval, onCancel, actionDetails }) => {
  const details = actionDetails as unknown as ActionDetails;
  const [step, setStep] = useState<number>(1);
  const [reason, setReason] = useState<string>('');
  const [auditTrail, setAuditTrail] = useState<AuditEntry[]>([]);
  const [isConfirmed, setIsConfirmed] = useState<boolean>(false);
  const [otpCode, setOtpCode] = useState<string>('');
  const [showOtpInput, setShowOtpInput] = useState<boolean>(false);
  const [otpVerifying, setOtpVerifying] = useState<boolean>(false);
  const [otpError, setOtpError] = useState<string>('');
  const { user } = useAuthStore();

  const protocolSteps = [
    "Action Identified",
    "Risk Assessment",
    "Stakeholder Notification",
    "Manual Review",
    "Security Validation",
    "Execution Authorization",
    "Post-Action Verification"
  ];

  useEffect(() => {
    // Load audit trail when component mounts
    setAuditTrail([
      { step: 1, status: 'completed', timestamp: new Date().toISOString(), actor: 'system', action: 'Action identified and logged' },
      { step: 2, status: 'completed', timestamp: new Date().toISOString(), actor: 'risk_engine', action: 'Automated risk assessment completed' },
      { step: 3, status: 'pending', timestamp: new Date().toISOString(), actor: 'notification_service', action: 'Notifying stakeholders...' }
    ]);
  }, [user]);

  const handleNextStep = () => {
    if (step < protocolSteps.length) {
      setStep(step + 1);
      setAuditTrail([...auditTrail, {
        step: step + 1,
        status: 'pending',
        timestamp: new Date().toISOString(),
        actor: 'system',
        action: `Step ${step + 1} initiated`
      }]);
    }
  };

  const handleApprove = () => {
    if (step === protocolSteps.length) {
      if (details.requiresOtp) {
        setShowOtpInput(true);
      } else {
        setIsConfirmed(true);
        onApproval(details.actionId);
      }
    }
  };

  const handleOtpSubmit = async () => {
    if (otpCode.length !== 6) return;

    setOtpVerifying(true);
    setOtpError('');
    try {
      await apiClient.post('/api/admin/verify-otp', { code: otpCode });
      setIsConfirmed(true);
      onApproval(details.actionId);
    } catch (err) {
      setOtpError(
        err instanceof Error && err.message
          ? err.message
          : 'OTP verification failed. Please try again.'
      );
    } finally {
      setOtpVerifying(false);
    }
  };

  const getStatusColor = (currentStep: number) => {
    if (currentStep < step) return 'bg-green-500';
    if (currentStep === step) return 'bg-yellow-500';
    return 'bg-gray-500';
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-2xl font-bold text-cyan-400">Human-in-the-Loop Protocol</h2>
            <button
              onClick={onCancel}
              className="text-gray-400 hover:text-white"
            >
              ✕
            </button>
          </div>

          <div className="mb-6 p-4 bg-gray-900 rounded-lg">
            <h3 className="text-lg font-semibold text-yellow-400 mb-2">Critical Action Pending</h3>
            <p className="text-gray-300">{details.description || 'A critical action requires human authorization.'}</p>
            <div className="mt-2 text-sm text-gray-400">
              <p><span className="font-medium">Action Type:</span> {details.type || 'System Operation'}</p>
              <p><span className="font-medium">Estimated Impact:</span> {details.impact || 'Medium'}</p>
              <p><span className="font-medium">Priority:</span> {details.priority || 'High'}</p>
            </div>
          </div>

          {/* Protocol Steps */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-purple-400 mb-3">Protocol Steps</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {protocolSteps.map((stepLabel, index) => (
                <div
                  key={index}
                  className={`p-3 rounded text-center ${
                    index + 1 < step ? 'bg-green-900 text-green-300' :
                    index + 1 === step ? 'bg-yellow-900 text-yellow-300 ring-2 ring-yellow-500' :
                    'bg-gray-700 text-gray-400'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-full mx-auto mb-1 flex items-center justify-center ${getStatusColor(index + 1)}`}>
                    {index + 1}
                  </div>
                  <div className="text-xs">{stepLabel}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Audit Trail */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-cyan-400 mb-3">Audit Trail</h3>
            <div className="bg-black bg-opacity-50 rounded p-3 max-h-40 overflow-y-auto">
              {auditTrail.map((entry, index) => (
                <div key={index} className="text-sm py-1 border-b border-gray-700 last:border-0">
                  <span className="text-gray-500 text-xs">[{new Date(entry.timestamp).toLocaleTimeString()}]</span>
                  <span className="mx-2">•</span>
                  <span className={`${
                    entry.status === 'completed' ? 'text-green-400' :
                    entry.status === 'pending' ? 'text-yellow-400' :
                    'text-gray-400'
                  }`}>
                    Step {entry.step}: {entry.action}
                  </span>
                  <span className="text-gray-500"> by {entry.actor}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Reason Input */}
          <div className="mb-6">
            <label className="block text-gray-300 mb-2">Provide reason for authorization:</label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full p-3 bg-gray-700 text-white rounded border border-gray-600 focus:outline-none focus:border-cyan-500"
              rows={3}
              placeholder="Explain why this action should be authorized..."
            />
          </div>

          {/* Action Buttons */}
          <div className="flex justify-between">
            <div>
              {step > 1 && (
                <button
                  onClick={() => setStep(step - 1)}
                  className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded mr-2"
                >
                  Previous
                </button>
              )}
              {step < protocolSteps.length && (
                <button
                  onClick={handleNextStep}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded"
                >
                  Next Step
                </button>
              )}
            </div>

            <div>
              <button
                onClick={onCancel}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded mr-2"
              >
                Cancel Action
              </button>

              {step === protocolSteps.length && (
                <button
                  onClick={handleApprove}
                  disabled={!reason.trim() || isConfirmed}
                  className={`px-4 py-2 rounded ${
                    !reason.trim() || isConfirmed
                      ? 'bg-gray-600 cursor-not-allowed'
                      : 'bg-green-600 hover:bg-green-700'
                  }`}
                >
                  {isConfirmed ? 'Action Confirmed' : 'Authorize Action'}
                </button>
              )}
            </div>
          </div>

          {/* OTP Modal */}
          {showOtpInput && (
            <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50">
              <div className="bg-gray-800 rounded-lg p-6 w-96">
                <h3 className="text-lg font-semibold text-yellow-400 mb-4">Security Verification</h3>
                <p className="text-gray-300 mb-4">Enter the OTP sent to your registered device to authorize this critical action.</p>

                <input
                  type="text"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="Enter 6-digit OTP"
                  maxLength={6}
                  disabled={otpVerifying}
                  className="w-full p-3 bg-gray-700 text-white rounded border border-gray-600 focus:outline-none focus:border-cyan-500 mb-4 disabled:opacity-60"
                />

                {otpError && (
                  <p className="text-sm text-red-400 mb-4">{otpError}</p>
                )}

                <div className="flex justify-end space-x-2">
                  <button
                    onClick={() => setShowOtpInput(false)}
                    disabled={otpVerifying}
                    className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded disabled:opacity-60"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleOtpSubmit}
                    disabled={otpCode.length !== 6 || otpVerifying}
                    className={`px-4 py-2 rounded ${
                      otpCode.length !== 6 || otpVerifying
                        ? 'bg-gray-600 cursor-not-allowed'
                        : 'bg-green-600 hover:bg-green-700'
                    }`}
                  >
                    {otpVerifying ? 'Verifying...' : 'Submit OTP'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Confirmation Message */}
          {isConfirmed && (
            <div className="mt-4 p-3 bg-green-900 text-green-300 rounded text-center">
              Action approved and authorized. Proceeding with execution...
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HumanInTheLoopProtocol;
