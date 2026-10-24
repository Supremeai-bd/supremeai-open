import { Link } from 'react-router-dom';
import { Sparkles, Home } from 'lucide-react';
import PromptTemplateLibrary from '../components/templates/PromptTemplateLibrary';

// ─── Component ───────────────────────────────────────────────────────────

export default function PromptTemplatePage() {
  return (
    <div className="flex flex-col h-screen bg-white dark:bg-slate-950">
      {/* Page Header */}
      <header className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <div className="px-6 py-4">
          {/* Breadcrumb */}
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm text-slate-400 mb-3">
            <Link
              to="/"
              className="hover:text-emerald-400 transition-colors flex items-center gap-1"
            >
              <Home className="w-3.5 h-3.5" />
              Home
            </Link>
            <span className="text-slate-600 select-none">›</span>
            <span className="font-medium text-slate-100">Prompt Template Library</span>
          </nav>

          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-violet-100 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900 dark:text-white">
                Prompt Template Library
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Browse, create, and manage reusable prompt templates to streamline your workflow.
                Click any template to preview its full content and fill in variables before inserting into chat.
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Library Content - Full Height */}
      <main className="flex-1 min-h-0">
        <PromptTemplateLibrary />
      </main>
    </div>
  );
}
