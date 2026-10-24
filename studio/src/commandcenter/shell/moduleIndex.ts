import {
  LayoutDashboard,
  Bot,
  Network,
  ListTodo,
  Users,
  Building2,
  Route,
  Server,
  Puzzle,
  Book,
  Gauge,
  FileText,
  Radio,
  Rocket,
  HeartPulse,
  Activity,
  Repeat,
  Shield,
  ScrollText,
  Inbox,
  Scale,
  KeyRound,
  Ban,
  DollarSign,
  Receipt,
  PiggyBank,
  TrendingUp,
  SlidersHorizontal,
  Settings,
  FolderKanban,
  DatabaseBackup,
  Lock,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { CommandModuleId } from '../data/types';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Shared Module Index
// বাংলা মন্তব্য: LeftRail ও ⌘K Command Palette-এর একক উৎস (registry-driven) —
// আগে নেভিগেশন শুধু LeftRail-এ ছিল, ফলে প্যালেট কখনোই তৈরি হতে পারত না।
// ═══════════════════════════════════════════════════════════════════════════

export interface RailItem {
  id: string;
  label: string;
  module: CommandModuleId;
  icon: LucideIcon;
  badge?: number;
}

export interface RailGroup {
  title: string;
  items: RailItem[];
}

export const COMMAND_GROUPS: RailGroup[] = [
  {
    title: 'DECK',
    items: [
      { id: 'deck', label: 'কমান্ড ডেক', module: 'deck', icon: LayoutDashboard },
    ],
  },
  {
    title: 'OPERATE',
    items: [
      { id: 'agents', label: 'এজেন্ট', module: 'agents', icon: Bot },
      { id: 'swarm', label: 'সোয়ার্ম', module: 'swarm', icon: Network },
      { id: 'tasks', label: 'টাস্ক ও কিউ', module: 'tasks', icon: ListTodo },
      { id: 'sessions', label: 'সেশন', module: 'sessions', icon: Users },
      { id: 'tenants', label: 'টেন্যান্ট', module: 'tenants', icon: Building2 },
    ],
  },
  {
    title: 'BUILD',
    items: [
      { id: 'router', label: 'মডেল রাউটার', module: 'router', icon: Route },
      { id: 'providers', label: 'প্রোভাইডার', module: 'providers', icon: Server },
      { id: 'skills', label: 'স্কিল', module: 'skills', icon: Puzzle },
      { id: 'memory', label: 'মেমোরি ও নলেজ', module: 'memory', icon: Book },
    ],
  },
  {
    title: 'OBSERVE',
    items: [
      { id: 'metrics', label: 'লাইভ মেট্রিক্স', module: 'metrics', icon: Gauge },
      { id: 'logs', label: 'লগ', module: 'logs', icon: FileText },
      { id: 'events', label: 'ইভেন্ট', module: 'events', icon: Radio },
      { id: 'ci', label: 'CI/CD', module: 'ci', icon: Rocket },
      { id: 'health', label: 'হেলথ ম্যাপ', module: 'health', icon: HeartPulse },
      { id: 'traffic', label: 'ট্রাফিক', module: 'traffic', icon: Activity },
      { id: 'evolution', label: 'ইভোলিউশন', module: 'evolution', icon: Repeat },
    ],
  },
  {
    title: 'SECURE',
    items: [
      { id: 'threats', label: 'থ্রেট', module: 'threats', icon: Shield },
      { id: 'audit', label: 'অডিট এক্সপ্লোরার', module: 'audit', icon: ScrollText },
      { id: 'approvals', label: 'অ্যাপ্রুভাল কিউ', module: 'approvals', icon: Inbox },
      { id: 'rules', label: 'রুলস ও পলিসি', module: 'rules', icon: Scale },
      { id: 'secrets', label: 'সিক্রেটস হেলথ', module: 'secrets', icon: KeyRound },
      { id: 'ratelimits', label: 'রেট লিমিট', module: 'ratelimits', icon: Ban },
    ],
  },
  {
    title: 'MONEY',
    items: [
      { id: 'cost', label: 'কস্ট অডিটর', module: 'cost', icon: DollarSign },
      { id: 'usage', label: 'ইউসেজ ও বিলিং', module: 'usage', icon: Receipt },
      { id: 'budget', label: 'বাজেট ক্যাপ', module: 'budget', icon: PiggyBank },
      { id: 'roi', label: 'ROI সেভিংস', module: 'roi', icon: TrendingUp },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { id: 'config', label: 'কনফিগ এডিটর', module: 'config', icon: SlidersHorizontal },
      { id: 'flags', label: 'ফিচার ফ্ল্যাগ', module: 'flags', icon: Settings },
      { id: 'workspaces', label: 'ওয়ার্কস্পেস', module: 'workspaces', icon: FolderKanban },
      { id: 'backups', label: 'ব্যাকআপ', module: 'backups', icon: DatabaseBackup },
      { id: 'deploy', label: 'ডিপ্লয় ও গেট', module: 'deploy', icon: Lock },
    ],
  },
];

/** Flat module index for the ⌘K palette. */
export const COMMAND_ITEMS: RailItem[] = COMMAND_GROUPS.flatMap((g) => g.items);
