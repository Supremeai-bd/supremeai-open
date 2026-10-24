import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/skillsService', () => ({
  fetchSkillCatalog: vi.fn(),
  searchSkills: vi.fn(),
  listInstalledSkills: vi.fn(),
  installSkill: vi.fn(),
  uninstallSkill: vi.fn(),
  getStatusBadge: (status: string) => ({ label: status, color: '#fff' }),
}));

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { MarketplacePage } from './MarketplacePage';
import * as skillsService from '../services/skillsService';

const mocked = vi.mocked(skillsService);

const sampleSkills: skillsService.SkillManifest[] = [
  {
    skill_id: 'web-scraper',
    name: 'Web Scraper',
    description: 'Scrape structured data from any public page.',
    version: '1.2.0',
    category: 'data',
    status: 'active',
    tags: ['scraping', 'html'],
    allowed_roles: ['user'],
    input_schema: {},
    output_schema: {},
  },
  {
    skill_id: 'chart-maker',
    name: 'Chart Maker',
    description: 'Render charts from tabular data.',
    version: '2.0.1',
    category: 'visuals',
    status: 'experimental',
    tags: ['charts'],
    allowed_roles: ['user'],
    input_schema: {},
    output_schema: {},
  },
];

const renderPage = () =>
  render(
    <MemoryRouter>
      <MarketplacePage />
    </MemoryRouter>,
  );

describe('MarketplacePage (ERR-B05)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchSkillCatalog.mockResolvedValue({
      skills: sampleSkills,
      total: sampleSkills.length,
      user_role: 'user',
    });
    mocked.listInstalledSkills.mockResolvedValue([]);
  });

  it('renders the catalog with category filters and install buttons', async () => {
    renderPage();
    expect(await screen.findAllByTestId('marketplace-skill-card')).toHaveLength(2);
    expect(screen.getByTestId('marketplace-category-all')).toBeInTheDocument();
    expect(screen.getByTestId('marketplace-category-data')).toBeInTheDocument();
    expect(screen.getByTestId('skill-install-btn-web-scraper')).toBeInTheDocument();
  });

  it('filters by category when a chip is clicked', async () => {
    renderPage();
    await screen.findAllByTestId('marketplace-skill-card');
    await userEvent.click(screen.getByTestId('marketplace-category-visuals'));
    await waitFor(() => {
      expect(screen.getAllByTestId('marketplace-skill-card')).toHaveLength(1);
    });
    expect(screen.getByText('Chart Maker')).toBeInTheDocument();
  });

  it('client-filters by search query and supports server search', async () => {
    renderPage();
    await screen.findAllByTestId('marketplace-skill-card');

    // Server search via button
    mocked.searchSkills.mockResolvedValue([sampleSkills[1]]);
    await userEvent.type(
      screen.getByTestId('marketplace-search-input'),
      'chart',
    );
    await userEvent.click(screen.getByTestId('marketplace-search-btn'));
    await waitFor(() => {
      expect(mocked.searchSkills).toHaveBeenCalledWith('chart');
    });
  });

  it('installs a skill and flips the card to Installed', async () => {
    mocked.installSkill.mockResolvedValue({
      success: true,
      skillId: 'web-scraper',
      installedVersion: '1.2.0',
      message: "Skill 'web-scraper' installed successfully",
    });
    renderPage();
    await screen.findAllByTestId('marketplace-skill-card');

    await userEvent.click(screen.getByTestId('skill-install-btn-web-scraper'));
    await waitFor(() => {
      expect(mocked.installSkill).toHaveBeenCalledWith('web-scraper');
    });
    expect(await screen.findByTestId('skill-uninstall-btn-web-scraper')).toBeInTheDocument();
    expect(screen.getByTestId('marketplace-notice')).toHaveTextContent(/installed/i);
  });

  it('uninstalls an installed skill', async () => {
    mocked.listInstalledSkills.mockResolvedValue([sampleSkills[0]]);
    mocked.uninstallSkill.mockResolvedValue(undefined);
    renderPage();
    expect(
      await screen.findByTestId('skill-uninstall-btn-web-scraper'),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('skill-uninstall-btn-web-scraper'));
    await waitFor(() => {
      expect(mocked.uninstallSkill).toHaveBeenCalledWith('web-scraper');
    });
    expect(
      await screen.findByTestId('skill-install-btn-web-scraper'),
    ).toBeInTheDocument();
  });

  it('shows an honest error state when the catalog fails', async () => {
    mocked.fetchSkillCatalog.mockRejectedValue(new Error('catalog unavailable'));
    renderPage();
    expect(await screen.findByTestId('marketplace-error')).toBeInTheDocument();
    expect(screen.getByText('catalog unavailable')).toBeInTheDocument();
  });

  it('shows empty state when nothing matches', async () => {
    renderPage();
    await screen.findAllByTestId('marketplace-skill-card');
    await userEvent.type(screen.getByTestId('marketplace-search-input'), 'zzz-no-match');
    await waitFor(() => {
      expect(screen.getByTestId('marketplace-empty')).toBeInTheDocument();
    });
  });
});
