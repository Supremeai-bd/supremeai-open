// বাংলা মন্তব্য: Storybook decorator (HOC) ইচ্ছাকৃতভাবে কম্পোনেন্ট ছাড়া এক্সপোর্ট করছে — react-refresh নিয়ম পুরো ফাইলে disable।
/* eslint-disable react-refresh/only-export-components */
import React from 'react';
import '../src/index.css';

const ThemeWrapper = ({ theme, Story }: { theme: string; Story: React.FC }) => {
  React.useEffect(() => {
    document.body.classList.remove('light', 'dark');
    document.body.classList.add(theme);
  }, [theme]);

  return (
    <div className={`theme-wrapper ${theme} min-h-screen p-8 bg-[var(--supremeai-color-bg-void-light)] dark:bg-[var(--supremeai-color-bg-void-dark)]`}>
      <Story />
    </div>
  );
};

interface StoryContext { globals: { theme: string } }
// বাংলা মন্তব্য: Storybook decorator (HOC) ইচ্ছাকৃতভাবে কম্পোনেন্ট ছাড়া এক্সপোর্ট করছে — react-refresh নিয়ম এড়াতে disable।
export const withTheme = (Story: React.FC, context: StoryContext) => {
  const theme = context.globals.theme || 'light';

  return <ThemeWrapper theme={theme} Story={Story} />;
};
