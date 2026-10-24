// RESTORE-AND-WIRE (2026-09-14): adapter page for the restored SettingsPage.
// The restored component takes (theme, toggleTheme) explicitly; this wrapper
// supplies them from the app ThemeProvider so the page can be routed directly.
import React from 'react';
import { useTheme } from '../../contexts/useTheme';
import { SettingsPage } from '../../components/dashboard/SettingsPage';

export const WorkspaceSettingsPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  return <SettingsPage theme={theme} toggleTheme={toggleTheme} />;
};

export default WorkspaceSettingsPage;
