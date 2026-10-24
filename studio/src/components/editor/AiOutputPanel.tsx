import React, { useEffect, useRef } from "react";

export interface AiOutput {
  title: string;
  content: string;
  kind: "markdown" | "plain" | "json";
  meta?: string;
}

interface Props {
  output: AiOutput | null;
  loading?: boolean;
  onClose: () => void;
}

/** AI অ্যাকশনগুলোর আউটপুট দেখানোর জন্য একটি সাধারণ panel। */
export const AiOutputPanel: React.FC<Props> = ({ output, loading, onClose }) => {
  const preRef = useRef<HTMLPreElement>(null);

  // নতুন আউটপুট এলে auto-scroll
  useEffect(() => {
    if (preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
  }, [output, loading]);

  if (!output && !loading) return null;

  return (
    <div className="absolute inset-0 z-40 bg-black/60 flex items-center justify-center p-6">
      <div className="bg-[#1e1e1e] border border-gray-700 rounded-lg shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-700 bg-[#252526] rounded-t-lg">
          <div className="flex items-center space-x-2">
            <span className="text-blue-400 font-bold text-sm">{output?.title || "SupremeAI"}</span>
            {loading && (
              <span className="text-xs px-2 py-0.5 bg-yellow-600/20 text-yellow-300 rounded animate-pulse">
                Analyzing…
              </span>
            )}
            {output?.meta && (
              <span className="text-xs px-2 py-0.5 bg-gray-700 text-gray-300 rounded">{output.meta}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-lg leading-none"
            aria-label="Close panel"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <pre
          ref={preRef}
          className="flex-1 min-h-0 overflow-auto p-4 text-[13px] leading-relaxed text-gray-300 font-mono whitespace-pre-wrap break-words"
        >
          {loading && !output
            ? "⏳ SupremeAI বুদ্ধিমত্তা কাজ করছে…"
            : output?.content || ""}
        </pre>
      </div>
    </div>
  );
};
