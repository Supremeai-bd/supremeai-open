import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const location = useLocation();
  const user = useAuthStore((state) => state.user);

  // বাংলা মন্তব্য: টেস্ট আইডি সহ নেভিগেশন আইটেম লিস্ট তৈরি করা হলো
  const navItems = [
    { id: "workspace", name: "Dashboard", path: "/workspace", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" },
    { id: "agent", name: "AI Assistant", path: "/workspace/agent", icon: "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" },
    { id: "ide", name: "Code Editor", path: "/workspace/ide", icon: "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" },
    { id: "skills", name: "Skills", path: "/skills-catalog", icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" },
    { id: "integrations", name: "Integrations", path: "/integrations", icon: "M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" },
    { id: "analytics", name: "Analytics", path: "/workspace/live", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
    { id: "profile", name: "Profile", path: "/profile", icon: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" },
  ];

  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 z-20 bg-black bg-opacity-50 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      {/* বাংলা মন্তব্য: টেস্টের সুবিধার্থে dashboard-sidebar আইডি যুক্ত করা হলো */}
      <aside
        data-testid="dashboard-sidebar"
        className={`fixed top-0 left-0 h-full w-64 bg-white dark:bg-slate-900 border-r border-gray-200 dark:border-slate-800 transform ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        } transition-transform duration-300 ease-in-out z-30 lg:translate-x-0 lg:static lg:inset-0`}
      >
        <div className="p-4">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-purple-500 to-fuchsia-500 flex items-center justify-center shadow-[0_0_14px_rgba(139,92,246,0.55)]">
              <span className="text-white font-bold">S</span>
            </div>
            <span className="font-bold text-lg bg-gradient-to-r from-indigo-500 to-fuchsia-500 bg-clip-text text-transparent dark:text-transparent">SupremeAI</span>
          </div>
        </div>

        <nav className="px-2 py-4">
          <ul className="space-y-1">
            {navItems.map((item) => (
              <li key={item.name}>
                <Link
                  to={item.path}
                  data-testid={`nav-${item.id}`}
                  onClick={onClose}
                  aria-current={location.pathname === item.path || location.pathname.startsWith(`${item.path}/`) ? 'page' : undefined}
                  className={`flex items-center px-4 py-3 text-base font-medium rounded-lg transition-all duration-200 ${
                    location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)
                      ? "bg-gradient-to-r from-indigo-500/20 to-fuchsia-500/10 text-indigo-700 dark:text-indigo-300 border-r-2 border-indigo-500 shadow-[inset_0_0_12px_rgba(99,102,241,0.12)]"
                      : "text-gray-700 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-800 hover:translate-x-0.5"
                  }`}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-5 w-5 mr-3"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d={item.icon}
                    />
                  </svg>
                  {item.name}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="absolute bottom-0 w-full p-4 border-t border-gray-200 dark:border-slate-800">
          <div className="flex items-center">
            <div className="w-10 h-10 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mr-3">
              <span className="text-green-800 dark:text-green-400 font-medium">
                {user ? user.name.charAt(0).toUpperCase() : 'U'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-800 dark:text-slate-200">
                {user ? user.name : 'Guest User'}
              </p>
              <p className="text-xs text-gray-500 dark:text-slate-500">
                {user ? user.email : 'guest@supremeai.dev'}
              </p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
