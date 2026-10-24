import { Search, Bell, Moon, Sun, User } from 'lucide-react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { useAuthStore } from '../../store/authStore';
import { useI18n } from '../../i18n/useI18n';
import { locales, type Locale } from '../../i18n/config';

export const Header = ({
  theme,
  toggleTheme,
}: {
  theme: 'dark' | 'light';
  toggleTheme: () => void;
}) => {
  const user = useAuthStore((state) => state.user);
  const { locale, setLocale } = useI18n();

  return (
    <div className="w-full flex items-center justify-between">
      <div className="flex-1 max-w-md">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--supremeai-color-neutral-500)]" />
          <Input
            placeholder="Search AI models, integrations..."
            className="pl-9 bg-[var(--supremeai-color-neutral-100)] dark:bg-[var(--supremeai-color-neutral-900)] border-none"
          />
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <select
          value={locale}
          onChange={(e) => {
            const next = e.target.value;
            if (locales.includes(next as Locale)) setLocale(next as Locale);
          }}
          className="bg-transparent border border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] text-xs rounded px-2 py-1 cursor-pointer outline-none focus:ring-1 focus:ring-[var(--supremeai-color-brand-500)] text-[var(--supremeai-color-neutral-500)] hover:text-foreground"
        >
          <option value="en" className="dark:bg-slate-950 text-foreground bg-slate-100">English (EN)</option>
          <option value="bn" className="dark:bg-slate-950 text-foreground bg-slate-100">বাংলা (BN)</option>
        </select>

        <Button variant="ghost" className="w-9 h-9 p-0 rounded-full">
          <Bell className="w-5 h-5 text-[var(--supremeai-color-neutral-500)]" />
        </Button>
        <Button
          variant="ghost"
          onClick={toggleTheme}
          className="w-9 h-9 p-0 rounded-full"
        >
          {theme === 'dark' ? (
            <Sun className="w-5 h-5 text-[var(--supremeai-color-neutral-500)]" />
          ) : (
            <Moon className="w-5 h-5 text-[var(--supremeai-color-neutral-500)]" />
          )}
        </Button>

        <div className="h-8 w-8 rounded-full bg-[var(--supremeai-color-neutral-100)] dark:bg-[var(--supremeai-color-neutral-900)] flex items-center justify-center border border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] overflow-hidden">
          {user?.avatarUrl ? (
            <img src={user.avatarUrl} alt={user.name} className="h-full w-full object-cover" />
          ) : (
            <User className="w-4 h-4 text-[var(--supremeai-color-neutral-500)]" />
          )}
        </div>
      </div>
    </div>
  );
};
