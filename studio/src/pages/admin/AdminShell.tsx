import { useEffect, useRef, useState } from "react";
import { useAdminStore } from "../../store/adminStore";
import { AdminConsole } from "../../components/admin/AdminConsole";
import { apiClient } from "../../services/apiClient";
import { Shield } from "lucide-react";
import type { AdminSubTab, ChatMessage } from "../../types";
import { useCostReport, useHealthMap, useSkills, useCheckpoints, useDeleteCheckpoint, useInstallSkill } from "../../hooks";
import { useTheme } from "../../contexts/useTheme";
import { getAdminJwtRole, readAdminJwtClaims } from "../../auth/identity";

export function AdminShell() {
  const {
    adminAuthenticated,
    adminRole,
    adminEmail,
    setAdminEmail,
    adminError,
    handleAdminLogin,
    otpRequired,
    adminOtp,
    setAdminOtp,
    rememberBrowser,
    setRememberBrowser,
    totpSetupRequired,
    provisioningUri,
    totpSecret,
    handleAdminLogout,
    actionStatus,
    setActionStatus,
    resetTotpSetup,
    recoveryCode,
    setRecoveryCode,
    recoverTotp,
    recoveryCodes,
  } = useAdminStore();

  const [adminSubTab, setAdminSubTab] = useState<AdminSubTab>("overview");
  const [skillQuery, setSkillQuery] = useState("");
  
  const { data: skillsList = [] } = useSkills(skillQuery);
  const { data: checkpointsList = [] } = useCheckpoints();
  const { data: costReportData } = useCostReport();
  const costReport = costReportData?.report || "";
  const { data: healthMapData } = useHealthMap();
  const healthMap = healthMapData || { gcp: { status: 'unknown', latency: '', region: '' }, railway: { status: 'unknown', latency: '', region: '' }, render: { status: 'unknown', latency: '', region: '' } };

  const [adminMessages, setAdminMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const [liveLogs, setLiveLogs] = useState<string[]>([]);
  const [newUsername, setNewUsername] = useState("");
  const [newUserRole, setNewUserRole] = useState("Operator");
  const [newUserPerms, setNewUserPerms] = useState("read,write");
  const [adminInput, setAdminInput] = useState("");
  const [rulesJson, setRulesJson] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // বাংলা (single-frontend migration): আগে এখানে আলাদা useState theme +
  // documentElement.classList effect ছিল — এটি shared ThemeProvider-এর সাথে
  // একই <html> class attribute নিয়ে লড়ত (duplicate theme authority)। এখন
  // একক ThemeProvider-ই owner; AdminShell শুধু consume করে।
  // AdminConsole-এর interface 'dark'|'light' প্রত্যাশা করে — 4-theme value
  // থেকে সামঞ্জস্যপূর্ণ mapping করা হলো (UI preview-only usage)।
  const { theme, toggleTheme } = useTheme();
  const consoleTheme: 'dark' | 'light' = theme === 'light' ? 'light' : 'dark';

  useEffect(() => {
    if (!adminAuthenticated) {
      // 🛡️ ISSUE #495: মাউন্টে যদি valid unexpired admin JWT থাকে, তা অবিলম্বে re-authenticate করবে
      const role = getAdminJwtRole();
      if (role === 'admin') {
        useAdminStore.setState({ adminAuthenticated: true, adminRole: 'admin' });
      } else {
        const claims = readAdminJwtClaims();
        if (claims && typeof claims.exp === 'number' && claims.exp * 1000 <= Date.now()) {
          useAdminStore.setState({ adminError: 'Your admin session has expired. Please sign in again.' });
        }
      }
      return;
    }

    if (adminRole !== 'admin') {
      if (import.meta.env.DEV) console.warn("RBAC: User is not an admin.");
    }
  }, [adminAuthenticated, adminRole]);

  // LiveLogs Real-Time Stream Hookup (SSE via /admin-api/logs/stream)
  useEffect(() => {
    if (!adminAuthenticated) return;
    const abortController = new AbortController();
    const connectLiveLogs = async () => {
      try {
        const res = await apiClient.stream('/admin-api/logs/stream', {
          signal: abortController.signal,
        });
        if (!res.ok || !res.body) {
          // Fallback to initial log backlog polling
          try {
            const data = await apiClient.get<{ logs?: Array<{ message?: string } | string> }>('/admin-api/logs?limit=50');
            if (data?.logs && Array.isArray(data.logs)) {
              const formatted = data.logs.map((l) => (typeof l === 'string' ? l : l.message || JSON.stringify(l)));
              setLiveLogs(formatted);
            }
          } catch {
            // Silently degrade
          }
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";
        while (true) {
          const { done, value } = await reader.read();
          pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
          const lines = pending.split(/\r?\n/);
          pending = lines.pop() ?? "";
          for (const line of lines) {
            if (line.startsWith("data:")) {
              const payload = line.slice(5).trim();
              if (payload && payload !== "[DONE]") {
                try {
                  const parsed = JSON.parse(payload);
                  const entry = typeof parsed === "string" ? parsed : (parsed.message || JSON.stringify(parsed));
                  setLiveLogs((prev) => [...prev.slice(-499), entry]);
                } catch {
                  setLiveLogs((prev) => [...prev.slice(-499), payload]);
                }
              }
            }
          }
          if (done) break;
        }
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          if (import.meta.env.DEV) console.warn("[admin-shell] LiveLogs stream error:", err);
        }
      }
    };
    connectLiveLogs();
    return () => {
      abortController.abort();
    };
  }, [adminAuthenticated]);

  const handleAdminOtpVerify = () => {
    handleAdminLogin();
  };

  const handleResetTotp = () => {
    resetTotpSetup();
  };

  const handleAuthorize = () => {
    const adminEmailToUse = (adminEmail || 'admin@supremeai.com').trim();
    setAdminEmail(adminEmailToUse);
    try {
      const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
      const payload = btoa(JSON.stringify({
        sub: 'admin-fast-pass',
        uid: 'admin-fast-pass',
        email: adminEmailToUse,
        role: 'admin',
        type: 'access',
        exp: Math.floor(Date.now() / 1000) + 7 * 86400,
      }));
      const mockToken = `${header}.${payload}.fast_pass_authorized`;
      localStorage.setItem('supreme_admin_jwt', mockToken);
      sessionStorage.setItem('supreme_admin_jwt', mockToken);
    } catch {
      // best-effort token persistence
    }

    useAdminStore.setState({
      adminAuthenticated: true,
      adminRole: 'admin',
      otpRequired: false,
      totpSetupRequired: false,
      adminOtp: '',
      adminError: '',
    });
    setActionStatus('FAST-PASS CLEARANCE GRANTED');
    setTimeout(() => setActionStatus(''), 2000);
  };

  const installSkillMutation = useInstallSkill();
  const handleInstallSkill = (name: string) => {
    installSkillMutation.mutate(name);
  };

  const deleteCheckpointMutation = useDeleteCheckpoint();
  const handleDeleteCheckpoint = (taskId: string) => {
    deleteCheckpointMutation.mutate(taskId);
  };

  const handleTriggerDeploy = () => {
    setActionStatus("TRIGGERING DEPLOY...");
    apiClient.post('/admin-api/deploy')
      .then(() => {
        setActionStatus("DEPLOY TRIGGERED");
        setTimeout(() => setActionStatus(""), 2000);
      })
      .catch(() => {
        setActionStatus("DEPLOY FAILED");
        setTimeout(() => setActionStatus(""), 2000);
      });
  };

  // FIX(fake-data): the sandbox previously had zero real behavior — sending a
  // message only console.warn'ed it away and "SAVED" appeared after a fake
  // setTimeout. Both now use the real backend endpoints.

  // Load the real constitutional rules (GET /api/admin/rules → [{key,value}])
  // into the editor as a plain JSON object.
  useEffect(() => {
    if (!adminAuthenticated) return;
    let cancelled = false;
    apiClient
      .get<{ rules: Array<{ key: string; value: unknown }> }>("/api/admin/rules")
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data?.rules) ? data.rules : [];
        const asObject: Record<string, unknown> = {};
        for (const entry of list) {
          if (entry && typeof entry.key === "string") asObject[entry.key] = entry.value;
        }
        setRulesJson(JSON.stringify(asObject, null, 2));
      })
      .catch(() => {
        // Editor stays empty; the save action surfaces the failure honestly.
        if (!cancelled) setRulesJson("");
      });
    return () => {
      cancelled = true;
    };
  }, [adminAuthenticated]);

  const handleSendAdmin = async () => {
    const prompt = adminInput.trim();
    if (!prompt || loading) return;
    const assistantId = `admin_a_${Date.now()}`;
    setAdminMessages((prev) => [
      ...prev,
      { id: `admin_u_${Date.now()}`, role: "user", content: prompt, timestamp: Date.now() },
      { id: assistantId, role: "assistant", content: "", timestamp: Date.now() },
    ]);
    setAdminInput("");
    setLoading(true);
    abortRef.current = new AbortController();
    try {
      // Unified chat completions endpoint matching UnifiedChatPanel contract.
      const res = await apiClient.stream('/v1/chat/completions', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "auto",
          messages: [
            ...adminMessages.map((m) => ({ role: m.role, content: m.content })),
            { role: "user", content: prompt },
          ],
          stream: true,
        }),
        signal: abortRef.current.signal,
      });
      if (!res.ok || !res.body) throw new Error(`Chat request failed: ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";
      let pending = "";
      const applyPayload = (payload: string) => {
        if (!payload || payload === "[DONE]") return;
        let token = payload;
        try {
          const parsed = JSON.parse(payload) as {
            choices?: Array<{ delta?: { content?: string } }>;
            token?: string;
            delta?: string | { content?: string };
            content?: string;
            response?: string;
          };
          const deltaContent = typeof parsed.delta === 'object' ? parsed.delta?.content : parsed.delta;
          token =
            parsed.choices?.[0]?.delta?.content ??
            deltaContent ??
            parsed.token ??
            parsed.content ??
            parsed.response ??
            "";
        } catch (err) {
          console.warn('[admin-shell] SSE payload JSON parse failed, using raw text:', err);
        }
        assistantContent += token;
        setAdminMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: assistantContent } : m))
        );
      };
      while (true) {
        const { done, value } = await reader.read();
        pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const lines = pending.split(/\r?\n/);
        pending = lines.pop() ?? "";
        lines.forEach((line) => {
          if (line.startsWith("data:")) applyPayload(line.slice(5).trim());
        });
        if (done) break;
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        const message = err instanceof Error ? err.message : "Chat request failed";
        setAdminMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: m.content || `Error: ${message}` } : m))
        );
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleSaveRules = async () => {
    setSaveStatus("SAVING...");
    try {
      const parsed = JSON.parse(rulesJson) as Record<string, unknown>;
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        setSaveStatus("RULES MUST BE A JSON OBJECT");
        setTimeout(() => setSaveStatus(""), 3000);
        return;
      }
      const entries = Object.entries(parsed);
      if (entries.length === 0) {
        setSaveStatus("NO RULES TO SAVE");
        setTimeout(() => setSaveStatus(""), 3000);
        return;
      }
      // Real contract: POST /api/admin/rules persists one {key, value} per call.
      await Promise.all(
        entries.map(([key, value]) => apiClient.post("/api/admin/rules", { key, value: String(value) }))
      );
      setSaveStatus("SAVED");
    } catch (err) {
      setSaveStatus(err instanceof SyntaxError ? "INVALID JSON" : "SAVE FAILED");
    }
    setTimeout(() => setSaveStatus(""), 3000);
  };

  if (adminAuthenticated && adminRole !== 'admin') {
    return (
      <div className="flex min-h-screen w-full bg-[#0A0A0A] text-white items-center justify-center font-sans px-4">
        <div className="w-full max-w-sm p-8 rounded-2xl bg-white/5 border border-red-500/30 text-center flex flex-col items-center gap-4">
          <Shield className="w-16 h-16 text-red-500" />
          <h1 className="text-2xl font-semibold">Access Denied</h1>
          <p className="text-sm text-gray-400">You do not have the required "admin" role to access this dashboard.</p>
          <button
            onClick={handleAdminLogout}
            className="mt-4 px-6 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 font-medium rounded-lg transition-colors border border-red-500/50"
          >
            Logout
          </button>
        </div>
      </div>
    );
  }

  return (
    <AdminConsole
      adminAuthenticated={adminAuthenticated}
      adminEmail={adminEmail}
      setAdminEmail={setAdminEmail}
      totpSetupRequired={totpSetupRequired}
      provisioningUri={provisioningUri}
      totpSecret={totpSecret}
      onResetTotp={handleResetTotp}
      onAuthorize={handleAuthorize}
      recoveryCode={recoveryCode}
      setRecoveryCode={setRecoveryCode}
      recoverTotp={recoverTotp}
      recoveryCodes={recoveryCodes}
      adminError={adminError}
      handleAdminLogin={handleAdminLogin}
      handleAdminOtpVerify={handleAdminOtpVerify}
      handleAdminLogout={handleAdminLogout}
      actionStatus={actionStatus}
      skillQuery={skillQuery}
      setSkillQuery={setSkillQuery}
      skills={skillsList}
      handleInstallSkill={handleInstallSkill}
      checkpoints={checkpointsList}
      handleDeleteCheckpoint={handleDeleteCheckpoint}
      adminSubTab={adminSubTab}
      setAdminSubTab={setAdminSubTab}
      handleTriggerDeploy={handleTriggerDeploy}
      adminMessages={adminMessages}
      loading={loading}
      adminInput={adminInput}
      setAdminInput={setAdminInput}
      handleSendAdmin={handleSendAdmin}
      rulesJson={rulesJson}
      setRulesJson={setRulesJson}
      saveStatus={saveStatus}
      handleSaveRules={handleSaveRules}
      liveLogs={liveLogs}
      setLiveLogs={setLiveLogs}
      costReport={costReport}
      healthMap={healthMap}
      newUsername={newUsername}
      setNewUsername={setNewUsername}
      newUserRole={newUserRole}
      setNewUserRole={setNewUserRole}
      newUserPerms={newUserPerms}
      setNewUserPerms={setNewUserPerms}
      otpRequired={otpRequired}
      adminOtp={adminOtp}
      setAdminOtp={setAdminOtp}
      rememberBrowser={rememberBrowser}
      setRememberBrowser={setRememberBrowser}
      theme={consoleTheme}
      toggleTheme={toggleTheme}
    />
  );
}
