
import { useEffect } from 'react';
import { getSupremeModelLabel, loadSupremeBranding, SUPREME_AVAILABLE_MODELS } from '../../lib/modelBranding';

const MODEL_META: Record<string, { cost: string; speed: string }> = {
  'gpt-4o': { cost: 'Standard', speed: 'Fast' },
  'gpt-4o-mini': { cost: 'Free', speed: 'Blazing' },
  'claude-3-5-sonnet': { cost: 'High', speed: 'Fast' },
  'gemini-1.5-pro': { cost: 'Free', speed: 'Fast' },
  'deepseek-chat': { cost: 'Free', speed: 'Blazing' },
  'llama-3-70b-versatile': { cost: 'Free', speed: 'Blazing' },
};

const getModelMeta = (id: string) => {
  return MODEL_META[id] || { cost: 'Free/Standard', speed: 'Fast' };
};

const models = SUPREME_AVAILABLE_MODELS.map((id) => ({
  id,
  name: getSupremeModelLabel(id),
  ...getModelMeta(id),
}));

interface StepProps {
  data: Record<string, string>;
  updateData: (updates: Record<string, string>) => void;
  nextStep: () => void;
}

const StepModelSelect = ({ data, updateData, nextStep }: StepProps) => {
  useEffect(() => {
    loadSupremeBranding();
  }, []);

  return (
    <div className="flex flex-col space-y-4 animate-fadeIn">
      <h3 className="text-xl font-semibold">Step 1: Choose your default brain</h3>
      <p className="text-gray-400 text-sm">You can always change this later. SupremeAI will route tasks to the best model automatically.</p>

      <div className="space-y-3 mt-4">
        {models.map(model => (
          <div
            key={model.id}
            onClick={() => updateData({ model: model.id })}
            className={`cursor-pointer p-4 rounded-lg border transition-all ${
              data.model === model.id
                ? 'bg-blue-600/20 border-blue-500 shadow-sm shadow-blue-500/20'
                : 'bg-gray-700/50 border-gray-600 hover:border-gray-500'
            }`}
          >
            <div className="flex justify-between items-center">
              <span className="font-medium text-gray-100">{model.name}</span>
              <div className="flex space-x-2 text-xs">
                <span className="px-2 py-1 bg-gray-800 rounded-md text-gray-300">{model.speed}</span>
                <span className="px-2 py-1 bg-gray-800 rounded-md text-gray-300">{model.cost}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-between pt-6">
        <span aria-hidden="true" />
        <button
          onClick={nextStep}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium shadow-lg shadow-blue-500/30"
        >
          Next
        </button>
      </div>
    </div>
  );
};

export default StepModelSelect;
