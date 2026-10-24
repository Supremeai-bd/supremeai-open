// বাংলা মন্তব্য: Task-12 ghost activation — KnowledgePage (আগে dead কম্পোনেন্ট)
// এখন ব্যাকএন্ড POST /api/knowledge/search + /api/knowledge/seed ব্যবহার করে।
// এই টেস্টগুলো প্রকৃত কনট্র্যাক্ট lock করে: POST method, {question} body,
// res.results unwrap, honest লোডিং/এরর/খালি অবস্থা।
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { KnowledgePage } from './KnowledgePage';
import { apiClient } from '../../services/apiClient';

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

describe('KnowledgePage (Task-12 orphan wiring)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('searches via POST /api/knowledge/search with {question} body', async () => {
    mockedPost.mockResolvedValue({
      results: [
        {
          id: 'core_doc_summarizer',
          title: 'core_doc_summarizer',
          content: '{"skill_id":"core_doc_summarizer"}',
          source: 'core_doc_summarizer.json',
          score: null,
        },
      ],
      total: 1,
      query: 'summarizer',
    });

    render(<KnowledgePage />);
    await userEvent.type(screen.getByTestId('knowledge-search-input'), 'summarizer');
    await userEvent.click(screen.getByTestId('knowledge-search-btn'));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/knowledge/search?limit=10',
        { question: 'summarizer' },
      );
    });
    // বাংলা: রেজাল্ট কার্ডে backend-derive করা title দৃশ্যমান হবে
    expect(await screen.findByText('core_doc_summarizer')).toBeInTheDocument();
    expect(screen.getByText(/source: core_doc_summarizer.json/)).toBeInTheDocument();
  });

  it('shows the honest empty state when search returns no results', async () => {
    mockedPost.mockResolvedValue({ results: [], total: 0, query: 'nothing' });

    render(<KnowledgePage />);
    await userEvent.type(screen.getByTestId('knowledge-search-input'), 'nothing');
    await userEvent.click(screen.getByTestId('knowledge-search-btn'));

    expect(await screen.findByText('No results found.')).toBeInTheDocument();
  });

  it('shows an honest error message when search fails', async () => {
    mockedPost.mockRejectedValue(new Error('backend offline'));

    render(<KnowledgePage />);
    await userEvent.type(screen.getByTestId('knowledge-search-input'), 'x');
    await userEvent.click(screen.getByTestId('knowledge-search-btn'));

    expect(await screen.findByText(/Search failed: backend offline/)).toBeInTheDocument();
  });

  it('seeds the knowledge base via POST /api/knowledge/seed', async () => {
    mockedPost.mockResolvedValue({ status: 'success', seeded: 1, message: 'Seeded 1 knowledge documents' });

    render(<KnowledgePage />);
    await userEvent.click(screen.getByTestId('seed-knowledge-btn'));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/knowledge/seed');
    });
    expect(
      await screen.findByText('Knowledge base seeded successfully.'),
    ).toBeInTheDocument();
  });
});
