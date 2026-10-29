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

vi.mock('../services/marketplaceService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/marketplaceService')>()),
  listMarketplacePlugins: vi.fn(),
  connectMarketplacePlugin: vi.fn(),
  discoverMarketplaceServer: vi.fn(),
}));

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { MarketplacePage } from './MarketplacePage';
import * as skillsService from '../services/skillsService';
import * as marketplaceService from '../services/marketplaceService';

const mocked = vi.mocked(skillsService);
const mockedPlugins = vi.mocked(marketplaceService);

const bundledCatalog = marketplaceService.BUNDLED_PLUGINS as unknown as marketplaceService.MarketplacePlugin[];

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

describe('MarketplacePage — MCP plugins (#1523)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchSkillCatalog.mockResolvedValue({
      skills: sampleSkills,
      total: sampleSkills.length,
      user_role: 'user',
    });
    mocked.listInstalledSkills.mockResolvedValue([]);
    mockedPlugins.listMarketplacePlugins.mockResolvedValue([...bundledCatalog]);
  });

  it('lists the plugin catalog when the MCP Plugins tab opens', async () => {
    renderPage();
    await userEvent.click(screen.getByTestId('marketplace-tab-plugins'));
    expect(await screen.findByTestId('marketplace-plugin-card-github')).toBeInTheDocument();
    expect(screen.getByTestId('marketplace-plugin-card-notion')).toBeInTheDocument();
    expect(mockedPlugins.listMarketplacePlugins).toHaveBeenCalledTimes(1);
    // Skills catalog is gated away on the plugins tab.
    expect(screen.queryByTestId('marketplace-skill-card')).not.toBeInTheDocument();
  });

  it('falls back to the bundled snapshot with an explicit offline notice', async () => {
    mockedPlugins.listMarketplacePlugins.mockRejectedValue(new Error('control plane down'));
    renderPage();
    await userEvent.click(screen.getByTestId('marketplace-tab-plugins'));
    expect(await screen.findByTestId('plugin-offline-notice')).toBeInTheDocument();
    expect(screen.getByTestId('marketplace-plugin-card-web-search')).toBeInTheDocument();
  });

  it('connects a hosted plugin end-to-end and offers descriptor discovery', async () => {
    mockedPlugins.connectMarketplacePlugin.mockResolvedValue({
      connection: {
        connectionId: 'mpconn_1_abc',
        pluginId: 'github',
        tenantId: 'tenant_default',
        remoteServerId: 'remote_123',
        credentialVaultRef: 'vault:github-token',
        endpointUsed: 'https://api.githubcopilot.com/mcp/',
        status: 'pending',
        connectedAt: new Date().toISOString(),
      },
      nextStep: 'Call client.discover_mcp_server with serverId=remote_123.',
    });
    mockedPlugins.discoverMarketplaceServer.mockResolvedValue({
      serverId: 'remote_123',
      toolCount: 2,
      tools: [{ name: 'create_issue' }, { name: 'list_prs' }],
    });
    renderPage();
    await userEvent.click(screen.getByTestId('marketplace-tab-plugins'));
    await userEvent.click(await screen.findByTestId('plugin-connect-btn-github'));
    // Endpoint prefilled from the hosted template.
    expect(screen.getByTestId('plugin-endpoint-input')).toHaveValue('https://api.githubcopilot.com/mcp/');
    await userEvent.type(screen.getByTestId('plugin-vaultref-input'), 'vault:github-token');
    await userEvent.click(screen.getByTestId('plugin-connect-submit'));
    await waitFor(() => {
      expect(mockedPlugins.connectMarketplacePlugin).toHaveBeenCalledWith({
        pluginId: 'github',
        credentialVaultRef: 'vault:github-token',
        endpoint: 'https://api.githubcopilot.com/mcp/',
      });
    });
    expect(await screen.findByTestId('plugin-discover-btn-github')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('plugin-discover-btn-github'));
    expect(await screen.findByTestId('plugin-connected-github')).toBeInTheDocument();
    // The notice reports the discovery; the card status shows the pin count.
    expect(screen.getByTestId('plugin-notice')).toHaveTextContent(/Discovered 2 tool\(s\) on remote_123/i);
    expect(screen.getByText(/2 tool\(s\) pinned/i)).toBeInTheDocument();
  });

  it('rejects plaintext tokens locally before any network call', async () => {
    renderPage();
    await userEvent.click(screen.getByTestId('marketplace-tab-plugins'));
    await userEvent.click(await screen.findByTestId('plugin-connect-btn-github'));
    // gitleaks:allow — detector fixture (14 chars, not a real 36-char PAT)
    await userEvent.type(screen.getByTestId('plugin-vaultref-input'), 'ghp_SuperSecret123');
    await userEvent.click(screen.getByTestId('plugin-connect-submit'));
    expect(await screen.findByTestId('plugin-notice')).toHaveTextContent(/live token/i);
    expect(mockedPlugins.connectMarketplacePlugin).not.toHaveBeenCalled();
  });

  it('demands an endpoint for self-hosted plugins', async () => {
    renderPage();
    await userEvent.click(screen.getByTestId('marketplace-tab-plugins'));
    await userEvent.click(await screen.findByTestId('plugin-connect-btn-telegram'));
    expect(screen.getByTestId('plugin-endpoint-input')).toHaveValue('');
    await userEvent.type(screen.getByTestId('plugin-vaultref-input'), 'vault:bot-token');
    await userEvent.click(screen.getByTestId('plugin-connect-submit'));
    expect(await screen.findByTestId('plugin-notice')).toHaveTextContent(/self-hosted/i);
    expect(mockedPlugins.connectMarketplacePlugin).not.toHaveBeenCalled();
  });
});
