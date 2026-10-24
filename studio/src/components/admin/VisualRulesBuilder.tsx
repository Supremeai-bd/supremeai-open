import { useState } from 'react';
import { Card, Badge } from '../ui';
import { Plus, Trash2, Play } from 'lucide-react';
import { useAdminRules, useSaveRules } from '../../hooks/useAdminApi';

interface Rule {
  id: string;
  name: string;
  condition: string;
  operator: 'equals' | 'contains' | 'starts_with' | 'regex';
  value: string;
  action: 'allow' | 'block' | 'warn' | 'log';
  severity: 'low' | 'medium' | 'high' | 'critical';
  enabled: boolean;
}

export function VisualRulesBuilder() {
  const { data: fetchedRules, isLoading } = useAdminRules();
  const saveRules = useSaveRules();

  const [localRules, setLocalRules] = useState<Rule[] | null>(null);
  const rules: Rule[] = localRules ?? (fetchedRules as Rule[] | undefined) ?? [];

  const updateRules = (next: Rule[]) => {
    setLocalRules(next);          // optimistic UI update
    saveRules.mutate(next, {      // real persist to services.rules_engine
      onError: () => setLocalRules(fetchedRules ?? []),  // rollback on failure
    });
  };

  const [selectedRule, setSelectedRule] = useState<Rule | null>(null);
  const [testingInput, setTestingInput] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);

  const addRule = () => {
    const newRule: Rule = {
      id: Date.now().toString(),
      name: 'New Rule',
      condition: 'user_input',
      operator: 'contains',
      value: '',
      action: 'log',
      severity: 'medium',
      enabled: true,
    };
    updateRules([...rules, newRule]);
    setSelectedRule(newRule);
  };

  const updateRule = (id: string, updates: Partial<Rule>) => {
    updateRules(rules.map(r => (r.id === id ? { ...r, ...updates } : r)));
    if (selectedRule?.id === id) {
      setSelectedRule({ ...selectedRule, ...updates });
    }
  };

  const deleteRule = (id: string) => {
    updateRules(rules.filter(r => r.id !== id));
    if (selectedRule?.id === id) setSelectedRule(null);
  };

  const testRule = () => {
    const matched = rules.filter(r => {
      if (!r.enabled) return false;
      const input = testingInput.toLowerCase();
      const value = r.value.toLowerCase();
      switch (r.operator) {
        case 'contains': return input.includes(value);
        case 'starts_with': return input.startsWith(value);
        case 'regex': {
          try {
            // ReDoS guard: bound pattern & test input lengths
            const safeInput = testingInput.slice(0, 10000);
            const safePattern = r.value.slice(0, 500);
            return new RegExp(safePattern).test(safeInput);
          } catch (err) {
            console.warn('[rules-builder] invalid regex pattern, treating as non-match:', err);
            return false;
          }
        }
        default: return false;
      }
    });
    if (matched.length === 0) {
      setTestResult('✅ No rules triggered');
    } else {
      setTestResult(`⚠️ ${matched.length} rule(s) triggered:\n${matched.map(r => `• ${r.name} → ${r.action.toUpperCase()}`).join('\n')}`);
    }
  };

  const severityColors: Record<string, 'danger' | 'warning' | 'info' | 'default'> = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'default',
  };

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      {isLoading && <p className="text-slate-400 text-xs font-mono p-6">Loading rules…</p>}
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          ⚖️ Visual Rules Builder
        </h2>
        <button
          onClick={addRule}
          className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#00f3ff] text-black text-[10px] font-bold font-mono uppercase hover:bg-cyan-400 transition-colors"
        >
          <Plus size={12} /> New Rule
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Rules Library" className="xl:col-span-2">
          <div className="flex flex-col gap-2">
            {rules.map(rule => (
              <div
                key={rule.id}
                onClick={() => setSelectedRule(rule)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  selectedRule?.id === rule.id
                    ? 'border-[#00f3ff]/50 bg-[#00f3ff]/10'
                    : 'border-slate-800 bg-slate-900/30 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-white font-mono">{rule.name}</span>
                    <Badge variant={severityColors[rule.severity]}>{rule.severity}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono ${
                      rule.action === 'block' ? 'bg-red-950 text-red-400' :
                      rule.action === 'warn' ? 'bg-yellow-950 text-yellow-400' :
                      rule.action === 'allow' ? 'bg-emerald-950 text-emerald-400' :
                      'bg-slate-800 text-slate-400'
                    }`}>
                      {rule.action.toUpperCase()}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteRule(rule.id); }}
                      className="text-red-400 hover:text-red-300 p-1"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  IF {rule.condition} {rule.operator} "{rule.value}" THEN {rule.action.toUpperCase()}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title={selectedRule ? 'Edit Rule' : 'Test Rules'} className="xl:col-span-1">
          {selectedRule ? (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 uppercase">Rule Name</label>
                <input
                  type="text"
                  value={selectedRule.name}
                  onChange={e => updateRule(selectedRule.id, { name: e.target.value })}
                  className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none focus:border-[#00f3ff] text-xs font-mono"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-400 uppercase">Operator</label>
                  <select
                    value={selectedRule.operator}
                    onChange={e => updateRule(selectedRule.id, { operator: e.target.value as Rule['operator'] })}
                    className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none text-xs font-mono"
                  >
                    <option value="contains">Contains</option>
                    <option value="starts_with">Starts With</option>
                    <option value="regex">Regex</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-400 uppercase">Action</label>
                  <select
                    value={selectedRule.action}
                    onChange={e => updateRule(selectedRule.id, { action: e.target.value as Rule['action'] })}
                    className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none text-xs font-mono"
                  >
                    <option value="allow">Allow</option>
                    <option value="warn">Warn</option>
                    <option value="block">Block</option>
                    <option value="log">Log</option>
                  </select>
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 uppercase">Pattern / Value</label>
                <input
                  type="text"
                  value={selectedRule.value}
                  onChange={e => updateRule(selectedRule.id, { value: e.target.value })}
                  className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none focus:border-[#00f3ff] text-xs font-mono"
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-400">Enabled</span>
                <button
                  onClick={() => updateRule(selectedRule.id, { enabled: !selectedRule.enabled })}
                  className={`w-8 h-4 rounded-full transition-colors ${selectedRule.enabled ? 'bg-[#00f3ff]' : 'bg-slate-700'}`}
                >
                  <div className={`w-3 h-3 rounded-full bg-white transition-transform ${selectedRule.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 uppercase">Test Input</label>
                <textarea
                  value={testingInput}
                  onChange={e => setTestingInput(e.target.value)}
                  placeholder="Enter text to test against rules..."
                  className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none focus:border-[#00f3ff] text-xs font-mono h-24 resize-none"
                />
              </div>
              <button
                onClick={testRule}
                className="flex items-center justify-center gap-2 bg-purple-500 hover:bg-purple-400 text-white font-bold px-4 py-1.5 rounded text-xs uppercase font-mono"
              >
                <Play size={10} /> Test Rules
              </button>
              {testResult && (
                <div className={`p-2.5 rounded text-[10px] font-mono whitespace-pre-wrap ${
                  testResult.startsWith('✅') ? 'bg-emerald-950/30 text-emerald-400 border border-emerald-900/50' :
                  'bg-yellow-950/30 text-yellow-400 border border-yellow-900/50'
                }`}>
                  {testResult}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
