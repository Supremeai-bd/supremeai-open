// apps/studio-client/src/pages/user/SkillCatalog.tsx
// বাংলা মন্তব্য: ব্যাকএন্ডের /api/skills/catalog এন্ডপয়েন্ট থেকে
// রিয়েল-টাইমে স্কিল ক্যাটালগ ফেচ ও রেন্ডার করার পেজ।
// ইউজার রোল ফিল্টারিং ব্যাকএন্ড JWT দ্বারা এনফোর্সড।

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSkillCatalog, getStatusBadge } from '../../services/skillsService';
import type { SkillManifest, SkillStatus } from '../../services/skillsService';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/Card';
import { useAuthStore } from '../../store/authStore';

const CATEGORY_ICONS: Record<string, string> = {
  knowledge: '🧠',
  document: '📄',
  code: '💻',
  browser: '🌐',
  data: '📊',
  security: '🔒',
  communication: '💬',
  default: '⚙️',
};

const StatusBadge: React.FC<{ status: SkillStatus }> = ({ status }) => {
  const { label, color } = getStatusBadge(status);
  return (
    <span
      style={{
        color,
        fontSize: '0.75rem',
        fontWeight: 600,
        padding: '2px 8px',
        borderRadius: '9999px',
        border: `1px solid ${color}`,
        display: 'inline-block',
      }}
    >
      {label}
    </span>
  );
};

const SkillCard: React.FC<{ skill: SkillManifest; onSelect: (s: SkillManifest) => void }> = ({ skill, onSelect }) => {
  const icon = CATEGORY_ICONS[skill.category?.toLowerCase()] ?? CATEGORY_ICONS.default;
  const isAvailable = skill.status === 'active' || skill.status === 'experimental';

  return (
    <Card
      onClick={() => isAvailable && onSelect(skill)}
      className={`transition-all duration-200 ${
        isAvailable
          ? 'cursor-pointer hover:scale-[1.02] hover:shadow-lg hover:border-[var(--supremeai-color-brand-primary-light)]'
          : 'opacity-50 grayscale cursor-not-allowed'
      }`}
    >
      <CardHeader>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ fontSize: '2.5rem', lineHeight: 1 }}>{icon}</div>
          <StatusBadge status={skill.status} />
        </div>
        <CardTitle style={{ marginTop: '0.75rem', fontSize: '1.05rem' }}>{skill.name}</CardTitle>
        <CardDescription>{skill.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {skill.tags?.slice(0, 4).map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: '0.7rem',
                padding: '2px 6px',
                borderRadius: '4px',
                background: 'var(--supremeai-color-surface-2, rgba(255,255,255,0.08))',
                color: 'var(--supremeai-color-neutral-400, #9ca3af)',
              }}
            >
              #{tag}
            </span>
          ))}
        </div>
        <p style={{ fontSize: '0.7rem', marginTop: '8px', color: 'var(--supremeai-color-neutral-500, #6b7280)' }}>
          v{skill.version} • {skill.category}
        </p>
      </CardContent>
    </Card>
  );
};

export const SkillCatalog: React.FC = () => {
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [selectedSkill, setSelectedSkill] = useState<SkillManifest | null>(null);
  const { role } = useAuthStore();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['skills-catalog'],
    queryFn: fetchSkillCatalog,
    staleTime: 60_000,
    retry: 2,
  });

  const skills = data?.skills ?? [];
  const userRole = data?.user_role ?? role ?? 'user';

  // ক্যাটাগরি লিস্ট ডায়নামিক্যালি তৈরি
  const categories = ['all', ...Array.from(new Set(skills.map((s) => s.category).filter(Boolean)))];

  const filtered = skills.filter((s) => {
    const matchSearch =
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.description.toLowerCase().includes(search.toLowerCase()) ||
      s.tags?.some((t) => t.toLowerCase().includes(search.toLowerCase()));
    const matchCategory = categoryFilter === 'all' || s.category === categoryFilter;
    return matchSearch && matchCategory;
  });

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          🧩 Skill Catalog
        </h1>
        <p style={{ color: 'var(--supremeai-color-neutral-500)', fontSize: '0.9rem' }}>
          Role: <strong>{userRole}</strong> · {data?.total ?? 0} skills available
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="🔍 Search skills..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: 1,
            minWidth: '220px',
            padding: '0.6rem 1rem',
            borderRadius: '8px',
            border: '1px solid var(--supremeai-color-border, #374151)',
            background: 'var(--supremeai-color-surface-2, #1f2937)',
            color: 'inherit',
            fontSize: '0.9rem',
          }}
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          style={{
            padding: '0.6rem 1rem',
            borderRadius: '8px',
            border: '1px solid var(--supremeai-color-border, #374151)',
            background: 'var(--supremeai-color-surface-2, #1f2937)',
            color: 'inherit',
            fontSize: '0.9rem',
            cursor: 'pointer',
          }}
        >
          {categories.map((cat) => (
            <option key={cat} value={cat}>
              {cat === 'all' ? '🗂️ All Categories' : `${CATEGORY_ICONS[cat] ?? '⚙️'} ${cat}`}
            </option>
          ))}
        </select>
        <button
          onClick={() => refetch()}
          style={{
            padding: '0.6rem 1.2rem',
            borderRadius: '8px',
            border: '1px solid var(--supremeai-color-border, #374151)',
            background: 'transparent',
            color: 'inherit',
            cursor: 'pointer',
            fontSize: '0.9rem',
          }}
        >
          🔄 Refresh
        </button>
      </div>

      {/* States */}
      {isLoading && (
        <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--supremeai-color-neutral-500)' }}>
          <div style={{ fontSize: '2rem', marginBottom: '1rem', animation: 'spin 1s linear infinite' }}>⏳</div>
          <p>Loading skill catalog...</p>
        </div>
      )}

      {isError && (
        <div style={{
          padding: '1.5rem',
          borderRadius: '12px',
          border: '1px solid var(--supremeai-color-danger, #ef4444)',
          background: 'rgba(239,68,68,0.08)',
          textAlign: 'center',
        }}>
          <p style={{ color: '#ef4444', fontWeight: 600 }}>⚠️ Failed to load catalog</p>
          <p style={{ fontSize: '0.85rem', color: 'var(--supremeai-color-neutral-500)', marginTop: '0.5rem' }}>
            {(error as Error)?.message}
          </p>
          <button onClick={() => refetch()} style={{ marginTop: '1rem', padding: '0.5rem 1.5rem', borderRadius: '8px', background: '#ef4444', color: '#fff', border: 'none', cursor: 'pointer' }}>
            Retry
          </button>
        </div>
      )}

      {/* Grid */}
      {!isLoading && !isError && (
        <>
          {filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--supremeai-color-neutral-500)' }}>
              <p style={{ fontSize: '1.5rem' }}>🔍</p>
              <p>No skills match your search.</p>
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '1.25rem',
            }}>
              {filtered.map((skill) => (
                <SkillCard key={skill.skill_id} skill={skill} onSelect={setSelectedSkill} />
              ))}
            </div>
          )}
        </>
      )}

      {/* Detail Modal */}
      {selectedSkill && (
        <div
          onClick={() => setSelectedSkill(null)}
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 9999, padding: '1rem',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--supremeai-color-surface-1, #111827)',
              border: '1px solid var(--supremeai-color-border, #374151)',
              borderRadius: '16px',
              padding: '2rem',
              maxWidth: '540px',
              width: '100%',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ fontSize: '1.3rem', fontWeight: 700 }}>
                {CATEGORY_ICONS[selectedSkill.category] ?? '⚙️'} {selectedSkill.name}
              </h2>
              <button onClick={() => setSelectedSkill(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.5rem', color: 'inherit' }}>✕</button>
            </div>
            <StatusBadge status={selectedSkill.status} />
            <p style={{ marginTop: '1rem', color: 'var(--supremeai-color-neutral-400)', lineHeight: 1.6 }}>{selectedSkill.description}</p>
            <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: 'var(--supremeai-color-neutral-500)' }}>
              <p><strong>ID:</strong> {selectedSkill.skill_id}</p>
              <p><strong>Version:</strong> v{selectedSkill.version}</p>
              <p><strong>Allowed Roles:</strong> {selectedSkill.allowed_roles?.join(', ') || 'All'}</p>
              <p><strong>Tags:</strong> {selectedSkill.tags?.join(', ')}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillCatalog;
