import React, { useEffect, useState } from 'react';
import { User, Shield, Key, Bell, Check, Lock, Moon, Sun } from 'lucide-react';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { apiClient } from '../services/apiClient';
import { useToast } from '../contexts/useToast';
import { useAuthStore } from '../store/authStore';
import { useTheme } from '../contexts/useTheme';

export const ProfilePage: React.FC = () => {
  const [saved, setSaved] = useState(false);
  const { user } = useAuthStore();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [preferredModel, setPreferredModel] = useState('DeepSeek-V3');
  const [jitOtpEnabled, setJitOtpEnabled] = useState(true);
  const { theme, toggleTheme } = useTheme();
  const { showToast } = useToast();
  const [notifications, setNotifications] = useState({
    email: true,
    push: true,
    digest: false
  });

  useEffect(() => {
    if (!user) return;
    setName(user.name || user.email.split('@')[0]);
    setEmail(user.email);
  }, [user]);

  const handleSave = async () => {
    try {
      // ERR-H01 FIX: real backend route is POST /api/preferences/ (no PUT
      // route exists); preferred_model maps to the contract's default_model.
      // Issue #2475: exact canonical path (trailing slash) — no 307 redirect hop.
      await apiClient.post('/api/preferences/', {
        theme: (theme === 'dark') ? 'dark' : 'light',
        default_model: preferredModel,
        profile: { name, email },
        security: { jit_otp_enabled: jitOtpEnabled },
        notifications,
      });
      setSaved(true);
      showToast('success', 'Profile preferences saved.');
      setTimeout(() => setSaved(false), 2000);
    } catch (error) {
      showToast('error', error instanceof Error ? error.message : 'Unable to save preferences.');
    }
  };

  const toggleNotification = (type: keyof typeof notifications) => {
    setNotifications(prev => ({
      ...prev,
      [type]: !prev[type]
    }));
  };

  const [avatarError, setAvatarError] = useState<string | null>(null);

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setAvatarError(null);
    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      setAvatarError('Only JPG, PNG, and WebP images are allowed.');
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setAvatarError('Avatar image size must be under 2MB.');
      return;
    }

    // Avatar validation passed
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    // বাংলা (single-frontend migration): page-level NavRail shell সরিয়ে একক shared
    // shell-এ আনা হলো (roadmap Rule 8: no duplicate global shells)।
    <WorkspaceLayout>
      <main className="p-8 max-w-4xl mx-auto w-full">
        <header className="mb-8">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/20 text-cyan-400">
              <User className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">User Profile & Preferences</h1>
              <p className="text-sm text-slate-400">Manage your identity, AI model defaults, and security shield settings</p>
            </div>
          </div>
        </header>

        <div className="space-y-6">
          {/* Profile Header */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-4 mb-4 md:mb-0">
                <div className="h-16 w-16 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
                  <span className="text-xl font-bold text-white">{name.split(' ').map(n => n[0]).join('')}</span>
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-slate-200">{name}</h2>
                  <p className="text-sm text-slate-400">{email}</p>
                  {avatarError && <p className="text-xs text-red-400 mt-1 font-mono">{avatarError}</p>}
                </div>
              </div>
              <div className="flex space-x-3">
                <label className="px-4 py-2 rounded-xl border border-slate-700 hover:bg-slate-800 transition-colors text-sm cursor-pointer inline-flex items-center justify-center">
                  <span>Change Avatar</span>
                  <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handleAvatarChange} className="hidden" />
                </label>
                <button className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 transition-colors text-sm">
                  Edit Profile
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column */}
            <div className="lg:col-span-2">
              {/* Identity Section */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4 mb-6">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200 border-b border-slate-800 pb-3">
                  <User className="h-5 w-5 text-cyan-400" /> Personal Information
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Full Name</label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full rounded-xl bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Email Address</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full rounded-xl bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Bio</label>
                  <textarea
                    rows={3}
                    defaultValue="Senior software developer with expertise in AI and full-stack development."
                    className="w-full rounded-xl bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-cyan-500 resize-none"
                  />
                </div>
              </div>

              {/* AI Preferences */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4 mb-6">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200 border-b border-slate-800 pb-3">
                  <Key className="h-5 w-5 text-cyan-400" /> Default AI Model Preferences
                </h2>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Preferred Code Engine</label>
                  <select
                    value={preferredModel}
                    onChange={(e) => setPreferredModel(e.target.value)}
                    className="w-full rounded-xl bg-slate-950 border border-slate-800 px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
                  >
                    <option value="DeepSeek-V3">SupremeAI Deep (Coding & Math Specialist)</option>
                    <option value="Kimi-K2.5">SupremeAI Reason (Bangla & Complex Reasoning)</option>
                    <option value="Together-Fallback">SupremeAI Collective (Auto-Fallback)</option>
                  </select>
                </div>
              </div>

              {/* Security Section */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200 border-b border-slate-800 pb-3">
                  <Shield className="h-5 w-5 text-emerald-400" /> Security Settings
                </h2>

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-slate-200">Dark Mode</p>
                      <p className="text-xs text-slate-400">Enable dark theme for better eye comfort</p>
                    </div>
                    <button
                      onClick={() => {
                        try {
                          toggleTheme();
                        } catch (storageError) {
                          console.warn('[v0] Theme preference could not be saved', storageError);
                        }
                      }}
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        (theme === 'dark') ? 'bg-cyan-500' : 'bg-slate-800'
                      }`}
                    >
                      <div
                        className={`w-5 h-5 rounded-full bg-white absolute top-0.5 transition-transform ${
                          (theme === 'dark') ? 'right-0.5' : 'left-0.5'
                        }`}
                      />
                    </button>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-slate-200">Just-In-Time (JIT) OTP Enforcement</p>
                      <p className="text-xs text-slate-400">Require single-use OTP verification before executing high-privilege actions.</p>
                    </div>
                    <button
                      onClick={() => setJitOtpEnabled(!jitOtpEnabled)}
                      className={`w-12 h-6 rounded-full transition-colors relative ${
                        jitOtpEnabled ? 'bg-cyan-500' : 'bg-slate-800'
                      }`}
                    >
                      <div
                        className={`w-5 h-5 rounded-full bg-white absolute top-0.5 transition-transform ${
                          jitOtpEnabled ? 'right-0.5' : 'left-0.5'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column */}
            <div className="lg:col-span-1">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-6">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200 border-b border-slate-800 pb-3">
                  <Bell className="h-5 w-5 text-cyan-400" /> Notifications
                </h2>

                <div className="space-y-4">
                  <label className="flex items-center justify-between">
                    <div className="flex items-center">
                      <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 mr-3">
                        <Moon className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-200">Email Notifications</p>
                        <p className="text-xs text-slate-400">Get updates via email</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={notifications.email}
                      onChange={() => toggleNotification('email')}
                      className="rounded text-cyan-500 focus:ring-cyan-500"
                    />
                  </label>

                  <label className="flex items-center justify-between">
                    <div className="flex items-center">
                      <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 mr-3">
                        <Bell className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-200">Push Notifications</p>
                        <p className="text-xs text-slate-400">Real-time app alerts</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={notifications.push}
                      onChange={() => toggleNotification('push')}
                      className="rounded text-cyan-500 focus:ring-cyan-500"
                    />
                  </label>

                  <label className="flex items-center justify-between">
                    <div className="flex items-center">
                      <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 mr-3">
                        <Sun className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-200">Weekly Digest</p>
                        <p className="text-xs text-slate-400">Summary of weekly updates</p>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={notifications.digest}
                      onChange={() => toggleNotification('digest')}
                      className="rounded text-cyan-500 focus:ring-cyan-500"
                    />
                  </label>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4 mt-6">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200 border-b border-slate-800 pb-3">
                  <Lock className="h-5 w-5 text-cyan-400" /> Account Security
                </h2>

                <div className="space-y-3">
                  <button className="w-full py-2.5 px-4 rounded-lg border border-slate-700 hover:bg-slate-800 text-sm text-slate-300 transition">
                    Change Password
                  </button>
                  <button className="w-full py-2.5 px-4 rounded-lg border border-slate-700 hover:bg-slate-800 text-sm text-slate-300 transition">
                    Manage API Keys
                  </button>
                  <button className="w-full py-2.5 px-4 rounded-lg border border-red-900/50 bg-red-900/20 hover:bg-red-900/30 text-red-400 text-sm transition">
                    Delete Account
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Action Button */}
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-slate-950 font-semibold text-sm transition-all shadow-lg shadow-cyan-500/20"
            >
              {saved ? <Check className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
              {saved ? 'Saved Successfully!' : 'Save Preferences'}
            </button>
          </div>
        </div>
      </main>
    </WorkspaceLayout>
  );
};

export default ProfilePage;
