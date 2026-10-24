import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronDown,
  ChevronRight,
  BrainCircuit,
  CheckCircle2,
  Sparkles,
  BadgePercent,
} from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────

interface ReasoningStep {
  content: string;
  score?: number;
  agent_id?: string;
}

interface ThinkingPanelProps {
  steps: ReasoningStep[];
  isThinking: boolean;
  finalAnswer?: string;
  confidence?: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function formatConfidence(value: number): string {
  return Math.round(value * 100).toString();
}

function getConfidenceColor(value: number): string {
  if (value >= 0.8) return 'text-emerald-500 dark:text-emerald-400';
  if (value >= 0.5) return 'text-amber-500 dark:text-amber-400';
  return 'text-red-500 dark:text-red-400';
}

function getConfidenceBgColor(value: number): string {
  if (value >= 0.8) return 'bg-emerald-500';
  if (value >= 0.5) return 'bg-amber-500';
  return 'bg-red-500';
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return 'bg-emerald-500';
  if (score >= 0.5) return 'bg-amber-500';
  return 'bg-red-500';
}

// ─── Sub-components ──────────────────────────────────────────────────────

function PulsingIndicator() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const percentage = Math.round(score * 100);

  return (
    <div className="flex items-center gap-2 mt-2">
      <div className="flex-1 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className={`h-full rounded-full ${getScoreColor(score)}`}
        />
      </div>
      <span className="text-xs font-mono text-slate-500 dark:text-slate-400 w-8 text-right">
        {percentage}%
      </span>
    </div>
  );
}

function AgentBadge({ agentId }: { agentId: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-wider bg-violet-100 dark:bg-violet-500/15 text-violet-700 dark:text-violet-400 border border-violet-200 dark:border-violet-500/25">
      <Sparkles className="w-3 h-3" />
      {agentId}
    </span>
  );
}

function StepCard({
  step,
  index,
  isLast,
}: {
  step: ReasoningStep;
  index: number;
  isLast: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, delay: index * 0.05 }}
      className="relative flex gap-3"
    >
      {/* Step number timeline */}
      <div className="flex flex-col items-center">
        <div className="flex items-center justify-center w-6 h-6 rounded-full bg-violet-100 dark:bg-violet-500/15 text-violet-600 dark:text-violet-400 text-xs font-bold flex-shrink-0">
          {index + 1}
        </div>
        {!isLast && (
          <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700 mt-1" />
        )}
      </div>

      {/* Step content */}
      <div className="flex-1 pb-4 min-w-0">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Step {index + 1}
          </span>
          {step.agent_id && <AgentBadge agentId={step.agent_id} />}
        </div>
        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap break-words">
          {step.content}
        </p>
        {step.score !== undefined && <ScoreBar score={step.score} />}
      </div>
    </motion.div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────

export function ThinkingPanel({
  steps,
  isThinking,
  finalAnswer,
  confidence,
}: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleToggle = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const hasContent = steps.length > 0 || isThinking;
  if (!hasContent && !finalAnswer) return null;

  return (
    <div className="w-full rounded-xl border border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/30 overflow-hidden">
      {/* Collapsed Header / Toggle */}
      <button
        type="button"
        onClick={handleToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-100 dark:hover:bg-slate-800/50 transition-colors"
        aria-expanded={isExpanded}
        aria-label={isExpanded ? 'Collapse reasoning' : 'Expand reasoning'}
      >
        {isThinking ? (
          <PulsingIndicator />
        ) : (
          <BrainCircuit className="w-4 h-4 text-violet-500 dark:text-violet-400" />
        )}

        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {isThinking ? (
            <span className="flex items-center gap-2">
              <span className="animate-pulse">💭 Thinking...</span>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                ({steps.length} {steps.length === 1 ? 'step' : 'steps'})
              </span>
            </span>
          ) : (
            <span>Reasoning ({steps.length} {steps.length === 1 ? 'step' : 'steps'})</span>
          )}
        </span>

        {/* Confidence badge in collapsed state */}
        {confidence !== undefined && !isThinking && (
          <span
            className={`ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${getConfidenceBgColor(confidence)} text-white`}
          >
            <BadgePercent className="w-3 h-3" />
            {formatConfidence(confidence)}%
          </span>
        )}

        <motion.div
          animate={{ rotate: isExpanded ? 0 : -90 }}
          transition={{ duration: 0.2 }}
          className="ml-auto text-slate-400"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </motion.div>
      </button>

      {/* Expanded Content */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.04, 0.62, 0.23, 0.98] }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1">
              {/* Reasoning Steps */}
              {steps.length > 0 && (
                <div className="space-y-0 max-h-72 overflow-y-auto pr-2 custom-scrollbar">
                  {steps.map((step, index) => (
                    <StepCard
                      key={index}
                      step={step}
                      index={index}
                      isLast={index === steps.length - 1}
                    />
                  ))}
                  {/* Thinking in progress indicator */}
                  {isThinking && (
                    <div className="relative flex gap-3">
                      <div className="flex flex-col items-center">
                        <div className="flex items-center justify-center w-6 h-6 rounded-full bg-violet-100 dark:bg-violet-500/15 flex-shrink-0">
                          <PulsingIndicator />
                        </div>
                      </div>
                      <p className="text-sm text-slate-400 dark:text-slate-500 italic animate-pulse">
                        Evaluating next step...
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Final Answer */}
              {finalAnswer && !isThinking && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                  className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700/50"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
                    <span className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                      Final Answer
                    </span>
                  </div>
                  <p className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed whitespace-pre-wrap break-words pl-6">
                    {finalAnswer}
                  </p>
                </motion.div>
              )}

              {/* Confidence Display */}
              {confidence !== undefined && !isThinking && (
                <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-700/50 flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                    Confidence
                  </span>
                  <div className="flex items-center gap-3">
                    <div className="w-24 h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${confidence * 100}%` }}
                        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.2 }}
                        className={`h-full rounded-full ${getConfidenceBgColor(confidence)}`}
                      />
                    </div>
                    <span
                      className={`text-sm font-bold ${getConfidenceColor(confidence)}`}
                    >
                      {formatConfidence(confidence)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
