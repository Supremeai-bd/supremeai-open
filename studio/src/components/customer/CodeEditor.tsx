import { useState } from 'react';
import Editor from '@monaco-editor/react';

interface CodeEditorProps {
  code: string;
  onChange: (code: string) => void;
}

const LANGUAGES = [
  { id: 'javascript', label: 'JavaScript', ext: 'js' },
  { id: 'typescript', label: 'TypeScript', ext: 'ts' },
  { id: 'python', label: 'Python', ext: 'py' },
  { id: 'html', label: 'HTML', ext: 'html' },
  { id: 'css', label: 'CSS', ext: 'css' },
  { id: 'json', label: 'JSON', ext: 'json' },
  { id: 'sql', label: 'SQL', ext: 'sql' },
  { id: 'markdown', label: 'Markdown', ext: 'md' },
];

const DEFAULT_CODE: Record<string, string> = {
  javascript: '// JavaScript\nconsole.warn("Hello, SupremeAI!");',
  typescript: '// TypeScript\nconst greeting: string = "Hello, SupremeAI!";\nconsole.warn(greeting);',
  python: '# Python\nprint("Hello, SupremeAI!")',
  html: '<!-- HTML -->\n<h1>Hello, SupremeAI!</h1>',
  css: '/* CSS */\nh1 {\n  color: #00f3ff;\n  font-family: "Space Grotesk", sans-serif;\n}',
  json: '{\n  "greeting": "Hello, SupremeAI!"\n}',
  sql: '-- SQL\nSELECT \'Hello, SupremeAI!\' AS greeting;',
  markdown: '# Hello, SupremeAI!\n\nWelcome to the **code editor**.',
};

export function CodeEditor({ code, onChange }: CodeEditorProps) {
  const [language, setLanguage] = useState('javascript');

  const handleLanguageChange = (newLang: string) => {
    setLanguage(newLang);
    const defaultCode = DEFAULT_CODE[newLang] || '// Start coding...';
    onChange(defaultCode);
  };

  const currentLang = LANGUAGES.find(l => l.id === language) || LANGUAGES[0];

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Tab bar with language selector */}
      <div className="h-10 bg-[#090b11] border-b border-slate-800 flex items-center px-2 gap-1 overflow-x-auto">
        {LANGUAGES.map(lang => (
          <button
            key={lang.id}
            onClick={() => handleLanguageChange(lang.id)}
            className={`text-[10px] px-2.5 py-1 rounded-t-md border-t border-l border-r font-mono transition-all whitespace-nowrap ${
              language === lang.id
                ? 'bg-[#161a27] text-[#00f3ff] border-[#00f3ff]/20 -mb-[1px]'
                : 'bg-transparent text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >
            {lang.label}
          </button>
        ))}
        {/* File extension badge */}
        <span className="ml-auto text-[9px] text-slate-600 font-mono pr-2">
          .{currentLang.ext}
        </span>
      </div>
      <div className="flex-1 relative">
        <Editor
          height="100%"
          language={language}
          theme="vs-dark"
          value={code}
          onChange={(val) => onChange(val || '')}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            fontFamily: "'JetBrains Mono', monospace",
            lineHeight: 24,
            padding: { top: 16 },
            scrollBeyondLastLine: false,
            smoothScrolling: true,
            cursorBlinking: 'smooth',
            cursorSmoothCaretAnimation: 'on'
          }}
        />
      </div>
    </div>
  );
}
