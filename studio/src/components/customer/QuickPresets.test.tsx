import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuickPresets } from './QuickPresets';

describe('QuickPresets', () => {
  it('renders the Quick Presets header', () => {
    render(<QuickPresets onSelectPreset={vi.fn()} />);
    expect(screen.getByText('Quick Presets • দ্রুত প্রিসেট')).toBeInTheDocument();
  });

  it('renders preset cards from all categories', () => {
    render(<QuickPresets onSelectPreset={vi.fn()} />);
    expect(screen.getByText('Python Algorithm')).toBeInTheDocument();
    expect(screen.getByText('JS Function')).toBeInTheDocument();
    expect(screen.getByText('React Component')).toBeInTheDocument();
    expect(screen.getByText('→ বাংলা')).toBeInTheDocument();
    expect(screen.getByText('→ Español')).toBeInTheDocument();
    expect(screen.getByText('Marketing Email')).toBeInTheDocument();
    expect(screen.getByText('Blog Post')).toBeInTheDocument();
    expect(screen.getByText('Error Explainer')).toBeInTheDocument();
    expect(screen.getByText('Code Explainer')).toBeInTheDocument();
  });

  it('renders preset descriptions', () => {
    render(<QuickPresets onSelectPreset={vi.fn()} />);
    expect(screen.getByText('Generate a Python binary search algorithm')).toBeInTheDocument();
    expect(screen.getByText('Translate English to Bengali')).toBeInTheDocument();
    expect(screen.getByText('Draft a startup marketing email')).toBeInTheDocument();
  });

  it('calls onSelectPreset with correct prompt when a preset is clicked', () => {
    const onSelectPreset = vi.fn();
    render(<QuickPresets onSelectPreset={onSelectPreset} />);

    fireEvent.click(screen.getByText('Python Algorithm'));
    expect(onSelectPreset).toHaveBeenCalledWith('Write a Python binary search algorithm with O(log n) complexity');
  });

  it('calls onSelectPreset for the JS Function preset', () => {
    const onSelectPreset = vi.fn();
    render(<QuickPresets onSelectPreset={onSelectPreset} />);

    fireEvent.click(screen.getByText('JS Function'));
    expect(onSelectPreset).toHaveBeenCalledWith('Write a JavaScript function to debounce a callback with configurable delay');
  });

  it('calls onSelectPreset for the Marketing Email preset', () => {
    const onSelectPreset = vi.fn();
    render(<QuickPresets onSelectPreset={onSelectPreset} />);

    fireEvent.click(screen.getByText('Marketing Email'));
    expect(onSelectPreset).toHaveBeenCalledWith('Write a professional marketing email for an AI-powered SaaS startup launch');
  });

  it('renders the Operator Core Ready status', () => {
    render(<QuickPresets onSelectPreset={vi.fn()} />);
    expect(screen.getByText('Operator Core Ready')).toBeInTheDocument();
  });

  it('filters presets by search', () => {
    render(<QuickPresets onSelectPreset={vi.fn()} />);
    const searchInput = screen.getByPlaceholderText('Search presets... সার্চ করুন...');
    fireEvent.change(searchInput, { target: { value: 'Python' } });
    expect(screen.getByText('Python Algorithm')).toBeInTheDocument();
    expect(screen.queryByText('Marketing Email')).not.toBeInTheDocument();
  });

  it('filters presets by category', () => {
    render(<QuickPresets onSelectPreset={vi.fn()} />);
    // বাংলা মন্তব্য: 'Code Explainer' কার্ডের সাথে দ্ব্যর্থতা এড়াতে সুনির্দিষ্টভাবে বাটন রোল দিয়ে ক্যাটাগরি ফিল্টার খোঁজা হচ্ছে
    fireEvent.click(screen.getByRole('button', { name: /Code/ }));
    expect(screen.getByText('Python Algorithm')).toBeInTheDocument();
    expect(screen.queryByText('Marketing Email')).not.toBeInTheDocument();
  });
});

