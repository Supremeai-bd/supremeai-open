import React, { useState } from "react";
import { Header } from "../core/Header";
import { Sidebar } from "../core/Sidebar";
import { useTheme } from "../../contexts/useTheme";

interface DashboardLayoutProps {
  title: string;
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ title, children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  return (
    <div className="dashboard-aurora flex h-screen bg-gray-50 dark:bg-slate-950">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header 
          title={title} 
          onToggleSidebar={toggleSidebar} 
          onToggleTheme={toggleTheme}
          theme={theme}
        />
        
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};
