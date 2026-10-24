import { useState } from 'react';
import StepModelSelect from './StepModelSelect';
import StepFirstChat from './StepFirstChat';

/**
 * Zero-config onboarding (Wave 2.6, issue #1243 — plan: customer_onboarding_flow.md).
 *
 * The plan's core thesis: "zero-config, 60s, কোনো API key না" — the very first
 * thing a new user should NOT be asked for is an API key. The previous flow
 * (`StepApiKey → StepModelSelect → StepFirstChat`) violated the plan by leading
 * with the API-key wall (CONFLICT_ANALYSIS verdict: plan correct, code wrong).
 *
 * New flow: StepModelSelect (Step 1) → StepFirstChat (Step 2) — first task in
 * 60 seconds, no key required. The old StepApiKey.tsx step file has been
 * removed (issue #1744): a founder-directed coder-pool verification confirmed
 * zero active imports, lifting the WAVE_MASTER_PLAN §10 rule 4 no-delete hold
 * for this file. History preserved in git; restore via `git log --follow`
 * on this directory if the API-key step is ever re-needed.
 */
const OnboardingWizard = () => {
  const [step, setStep] = useState(1);
  const [onboardingData, setOnboardingData] = useState({
    model: 'gpt-4o',
    firstPrompt: ''
  });

  const nextStep = () => setStep((prev) => prev + 1);
  const prevStep = () => setStep((prev) => prev - 1);

  const handleUpdate = (data: Partial<typeof onboardingData>) => {
    setOnboardingData((prev) => ({ ...prev, ...data }));
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-xl w-full bg-gray-800 rounded-xl shadow-xl p-8 border border-gray-700">
        <h2 className="text-3xl font-bold mb-6 text-center text-blue-400">Welcome to SupremeAI 2.0</h2>

        {/* Progress Bar */}
        <div className="flex justify-between mb-8">
          {[1, 2].map((num) => (
            <div key={num} className={`w-1/2 h-2 rounded-full mx-1 ${step >= num ? 'bg-blue-500' : 'bg-gray-600'}`} />
          ))}
        </div>

        {/* Steps — zero-config: model first, first chat second, no API key wall */}
        {step === 1 && <StepModelSelect data={onboardingData} updateData={handleUpdate} nextStep={nextStep} />}
        {step === 2 && <StepFirstChat data={onboardingData} updateData={handleUpdate} prevStep={prevStep} />}
      </div>
    </div>
  );
};

export default OnboardingWizard;
