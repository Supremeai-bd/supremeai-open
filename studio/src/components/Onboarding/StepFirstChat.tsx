
interface StepFirstChatData {
  firstPrompt?: string;
  [key: string]: unknown;
}

interface StepFirstChatProps {
  data: StepFirstChatData;
  updateData: (partial: Partial<StepFirstChatData>) => void;
  prevStep: () => void;
}

const StepFirstChat = ({ data, updateData, prevStep }: StepFirstChatProps) => {
  const completeOnboarding = () => {
    // In real app, we'd send data to backend here
    console.warn("Onboarding complete:", data);
    window.location.href = "/studio";
  };

  return (
    <div className="flex flex-col space-y-4 animate-fadeIn">
      <h3 className="text-xl font-semibold">Step 2: Ready for launch 🚀</h3>
      <p className="text-gray-400 text-sm">What would you like SupremeAI to build or help you with today?</p>

      <div className="space-y-2 mt-4">
        <textarea
          rows={4}
          placeholder="e.g. Build a fully functional e-commerce backend in FastAPI..."
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all resize-none"
          value={data.firstPrompt}
          onChange={(e) => updateData({ firstPrompt: e.target.value })}
        />
      </div>

      <div className="flex justify-between pt-6">
        <button
          onClick={prevStep}
          className="px-6 py-2 text-gray-400 hover:text-white transition-colors"
        >
          Back
        </button>
        <button
          onClick={completeOnboarding}
          className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white rounded-lg transition-all font-bold shadow-lg shadow-purple-500/30 transform hover:scale-105"
        >
          Start Building
        </button>
      </div>
    </div>
  );
};

export default StepFirstChat;
