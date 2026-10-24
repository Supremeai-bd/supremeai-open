import type { Meta, StoryObj } from '@storybook/react';
import { Input } from './Input';

const meta: Meta<typeof Input> = {
  title: 'Design System/UI/Input',
  component: Input,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    error: { control: 'text' },
    helperText: { control: 'text' },
    disabled: { control: 'boolean' },
    placeholder: { control: 'text' },
  },
};

export default meta;
type Story = StoryObj<typeof Input>;

export const Default: Story = {
  args: {
    placeholder: 'Enter your name...',
  },
};

export const WithLabel: Story = {
  args: {
    label: 'Email Address',
    placeholder: 'john@example.com',
  },
};

export const WithHelperText: Story = {
  args: {
    label: 'Username',
    placeholder: '@johndoe',
    helperText: 'This will be your public display name.',
  },
};

export const WithError: Story = {
  args: {
    label: 'Password',
    type: 'password',
    placeholder: '••••••••',
    error: 'Password must be at least 8 characters long.',
  },
};

export const Disabled: Story = {
  args: {
    label: 'Disabled Input',
    placeholder: 'You cannot type here',
    disabled: true,
  },
};
