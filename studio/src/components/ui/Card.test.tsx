import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './Card';
import React from 'react';

describe('Card', () => {
  it('renders basic card correctly', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Desc</CardDescription>
        </CardHeader>
        <CardContent>Content</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>
    );
    expect(screen.getByText('Title')).toBeDefined();
    expect(screen.getByText('Desc')).toBeDefined();
    expect(screen.getByText('Content')).toBeDefined();
    expect(screen.getByText('Footer')).toBeDefined();
  });

  it('renders card with title and icon props', () => {
    render(
      <Card title="Prop Title" icon={<span>⭐</span>}>
        Card Body
      </Card>
    );
    expect(screen.getByText('Prop Title')).toBeDefined();
    expect(screen.getByText('⭐')).toBeDefined();
    expect(screen.getByText('Card Body')).toBeDefined();
  });
});
