import React, { useState } from 'react';
import { Check, Copy, Link2, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { formatViewerValue, loadMcpViewerData, normalizeMcpUrl, type McpViewerData } from '../../services/mcpViewer';

type ConnectionState = 'idle' | 'connecting' | 'connected' | 'error';

function DataBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-background/40 p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground">{formatViewerValue(value)}</pre>
    </div>
  );
}

function friendlyViewerError(error: unknown): string {
  const status = error && typeof error === 'object' && 'status' in error ? (error as { status?: number }).status : undefined;
  if (status === 401 || status === 403) return 'এই serverটি private। Viewer access পেতে server owner-এর দেওয়া access দিন।';
  if (status === 404) return 'এই URL-এ viewer data পাওয়া যায়নি। URL ঠিক আছে কি না দেখুন।';
  if (status === 429) return 'Server এখন ব্যস্ত। একটু পরে আবার চেষ্টা করুন।';
  if (error instanceof DOMException && error.name === 'TimeoutError') return 'Server উত্তর দিতে দেরি করছে। আবার চেষ্টা করুন।';
  if (error instanceof TypeError) return 'Server-এ যোগাযোগ করা যাচ্ছে না। URL ও server status দেখুন।';
  return error instanceof Error ? error.message : 'এই server থেকে data পড়া যাচ্ছে না। আবার চেষ্টা করুন।';
}

function ViewerResults({ data }: { data: McpViewerData }) {
  const sections = [
    ['Server', data.server],
    ['Health', data.health],
    ['Dashboard', data.dashboard],
    ['Capabilities', data.capabilities],
    ['Resources', data.resources],
    ['Tools', data.tools],
  ] as const;
  const visibleSections = sections.filter(([, value]) => value !== null && (Array.isArray(value) ? value.length > 0 : Object.keys(value as object).length > 0));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-sm font-medium text-emerald-600"><Check size={16} /> Viewer access connected</div>
      {visibleSections.length ? visibleSections.map(([title, value]) => <DataBlock key={title} title={title} value={value} />) : <p className="text-sm text-muted-foreground">The server connected but returned no viewer data.</p>}
    </div>
  );
}

// This is intentionally a read-only, URL-driven viewer. Do not add server
// management, tool execution, memory controls, or policy editing here without
// an explicit product requirement.
export const MCPConnector: React.FC = () => {
  const [url, setUrl] = useState('');
  const [token, setToken] = useState('');
  const [state, setState] = useState<ConnectionState>('idle');
  const [message, setMessage] = useState('');
  const [data, setData] = useState<McpViewerData | null>(null);
  const [copied, setCopied] = useState(false);

  const copyServerUrl = async () => {
    const normalizedUrl = normalizeMcpUrl(url);
    if (!normalizedUrl) return;
    await navigator.clipboard.writeText(normalizedUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const connect = async () => {
    setState('connecting');
    setMessage('');
    setData(null);
    try {
      const normalizedUrl = normalizeMcpUrl(url);
      const viewerData = await loadMcpViewerData(normalizedUrl, token);
      setUrl(normalizedUrl);
      setData(viewerData);
      setState('connected');
    } catch (error) {
      setState('error');
      setMessage(friendlyViewerError(error));
    }
  };

  return (
    <section className="font-bengali mx-auto mt-8 flex max-w-4xl flex-col gap-5">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-[var(--supremeai-color-brand-primary)]"><Link2 size={16} /><span className="text-xs font-semibold uppercase tracking-[0.18em]">MCP Viewer</span></div>
        <h2 className="text-2xl font-semibold tracking-tight text-balance">সার্ভারের data দেখুন</h2>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">শুধু URL দিন। Login বা account ছাড়াই read-only data দেখা যাবে, যদি serverটি public viewer access দেয়।</p>
      </div>

      <Card className="overflow-hidden" title="URL দিন এবং খুলুন" icon={<Link2 size={20} />}>
        <form className="flex flex-col gap-4 px-4 pb-5 sm:px-6" onSubmit={(event) => { event.preventDefault(); void connect(); }}>
          <label className="flex flex-col gap-2 text-sm font-medium">
            MCP server URL
            <span className="font-normal leading-5 text-muted-foreground">যেমন: https://your-server.example.com/mcp</span>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input value={url} onChange={(event) => { setUrl(event.target.value); setState('idle'); setMessage(''); setCopied(false); }} placeholder="https://..." inputMode="url" autoComplete="url" aria-describedby="viewer-help" className="h-11 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring" />
              <Button type="button" variant="secondary" onClick={() => void copyServerUrl()} disabled={!url.trim()} aria-label="Copy MCP server URL">
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? 'কপি হয়েছে' : 'URL কপি করুন'}
              </Button>
            </div>
          </label>
          <p id="viewer-help" className="text-xs leading-5 text-muted-foreground">Public server হলে আর কিছু লাগবে না। Private server হলে তবেই নিচের optional access field ব্যবহার করুন।</p>
          <details className="rounded-md border border-border/60 px-3 py-2 text-sm">
            <summary className="cursor-pointer font-medium">Token দরকার হলে এখানে দিন</summary>
            <label className="mt-3 flex flex-col gap-2 text-sm">
              Viewer token <span className="font-normal text-muted-foreground">(optional)</span>
              <input type="password" value={token} onChange={(event) => { setToken(event.target.value); setState('idle'); setMessage(''); }} placeholder="শুধু private server-এর জন্য" autoComplete="off" className="h-11 rounded-md border bg-background px-3 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring" />
            </label>
          </details>
          <Button type="submit" state={state === 'connecting' ? 'loading' : 'default'} disabled={!url.trim() || state === 'connecting'}>{state === 'connected' ? <Check size={16} /> : <Link2 size={16} />}{state === 'connected' ? 'আবার data দেখুন' : 'খুলুন'}</Button>
        </form>
      </Card>

      {state === 'connecting' && <p role="status" className="rounded-lg border border-border/60 bg-background/50 p-4 text-sm leading-6 text-muted-foreground">সার্ভারের সঙ্গে যোগাযোগ হচ্ছে… একটু অপেক্ষা করুন।</p>}
      {message && <div role="alert" className="flex items-start justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm leading-6 text-destructive"><span>{message}</span><div className="flex shrink-0 items-center gap-2"><button type="button" className="font-semibold underline underline-offset-2" onClick={() => void connect()}>আবার চেষ্টা করুন</button><button type="button" onClick={() => setMessage('')} aria-label="বার্তাটি বন্ধ করুন"><X size={16} /></button></div></div>}
      {data && <ViewerResults data={data} />}
    </section>
  );
};
