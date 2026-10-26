/**
 * studio/src/pages/AcademyHubPage.tsx — Interactive AI Academies (Infinity plan Way 5).
 *
 * বাংলা: ফ্রি ইন্টারেক্টিভ একাডেমি হাব — lessons + quiz + XP, প্রোগ্রেস
 * সম্পূর্ণ localStorage-এ (Infinity প্যাটার্ন)। কোর্স = studio/src/content/
 * academies/* এ নতুন ডেটা ফাইল — কম্পোনেন্ট অপরিবর্তিত।
 *
 * Self-contained: React-only, Tailwind + tokens. No backend calls; progress
 * never leaves the browser (documented on-page).
 *
 * Route (public, INTEGRATION.diff provided):
 *   <Route path="/academies" element={<PublicPageShell><AcademyHubPage /></PublicPageShell>} />
 */

import { useCallback, useMemo, useState } from 'react';
import { academies, type Academy, type Lesson } from '../content/academies/mcpAcademy';

const STORAGE_KEY = 'supremeai.academy.progress.v1';

interface Progress {
  xp: number;
  completedLessons: string[]; // lesson ids across all academies
  quizScores: Record<string, number>; // lesson id -> best score 0..1
}

function loadProgress(): Progress {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { xp: 0, completedLessons: [], quizScores: {} };
    const parsed = JSON.parse(raw) as Partial<Progress>;
    return {
      xp: Number(parsed.xp) || 0,
      completedLessons: Array.isArray(parsed.completedLessons) ? parsed.completedLessons : [],
      quizScores: parsed.quizScores && typeof parsed.quizScores === 'object' ? parsed.quizScores : {},
    };
  } catch {
    return { xp: 0, completedLessons: [], quizScores: {} };
  }
}

function saveProgress(p: Progress): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* private mode / storage full — progress stays session-only, page still works */
  }
}

function lessonXp(lesson: Lesson): number {
  return 10 + lesson.quiz.length * 5;
}

function QuizBlock({
  lesson,
  onScored,
}: {
  lesson: Lesson;
  onScored: (score: number) => void;
}) {
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [graded, setGraded] = useState(false);

  const correct = useMemo(
    () => lesson.quiz.filter((q, i) => answers[i] === q.answerIndex).length,
    [answers, lesson.quiz],
  );

  const grade = () => {
    setGraded(true);
    onScored(lesson.quiz.length ? correct / lesson.quiz.length : 0);
  };

  if (!lesson.quiz.length) return null;

  return (
    <div className="mt-6 space-y-4">
      {lesson.quiz.map((q, qi) => (
        <fieldset key={qi} className="rounded-lg border border-white/10 bg-black/30 p-4">
          <legend className="px-1 text-sm font-medium text-white/90">{q.prompt}</legend>
          <div className="mt-2 space-y-1.5">
            {q.options.map((opt, oi) => {
              const chosen = answers[qi] === oi;
              const isAnswer = graded && oi === q.answerIndex;
              const isWrongPick = graded && chosen && oi !== q.answerIndex;
              return (
                <label
                  key={oi}
                  className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm ${
                    isAnswer
                      ? 'border-emerald-400/50 bg-emerald-400/10 text-emerald-100'
                      : isWrongPick
                        ? 'border-red-400/50 bg-red-400/10 text-red-100'
                        : 'border-white/10 text-white/80 hover:border-white/25'
                  }`}
                >
                  <input
                    type="radio"
                    name={`${lesson.id}-${qi}`}
                    checked={chosen}
                    onChange={() => {
                      setAnswers((a) => ({ ...a, [qi]: oi }));
                      setGraded(false);
                    }}
                    disabled={graded}
                    className="accent-emerald-400"
                  />
                  {opt}
                </label>
              );
            })}
          </div>
          {graded && (
            <p className="mt-2 text-xs text-white/60">💡 {q.explain}</p>
          )}
        </fieldset>
      ))}
      <div className="flex items-center gap-3">
        {!graded ? (
          <button
            type="button"
            onClick={grade}
            disabled={Object.keys(answers).length < lesson.quiz.length}
            className="rounded-lg border border-indigo-400/40 bg-indigo-400/10 px-4 py-2 text-sm text-indigo-100 disabled:opacity-40"
          >
            Grade answers
          </button>
        ) : (
          <span className="font-mono text-sm text-white/80">
            score: {correct}/{lesson.quiz.length}
          </span>
        )}
      </div>
    </div>
  );
}

function LessonCard({
  academy,
  lesson,
  index,
  done,
  bestScore,
  onComplete,
}: {
  academy: Academy;
  lesson: Lesson;
  index: number;
  done: boolean;
  bestScore: number;
  onComplete: (lessonId: string, score: number, xp: number) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <article
      className={`rounded-xl border p-4 transition ${
        done ? 'border-emerald-400/30 bg-emerald-400/[0.04]' : 'border-white/10 bg-white/[0.02]'
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-3">
          <span className="font-mono text-xs text-white/40">{String(index + 1).padStart(2, '0')}</span>
          <span className="text-sm font-medium text-white">{lesson.title}</span>
          {done && <span className="text-xs text-emerald-300">✓ done</span>}
          {bestScore > 0 && (
            <span className="text-xs text-white/50">best {Math.round(bestScore * 100)}%</span>
          )}
        </span>
        <span className="font-mono text-xs text-white/40">{lesson.minutes} min</span>
      </button>
      {open && (
        <div className="mt-4">
          {lesson.body.split('\n\n').map((para, i) => (
            <p key={i} className="mb-3 text-sm leading-relaxed text-white/75">
              {para}
            </p>
          ))}
          <QuizBlock
            lesson={lesson}
            onScored={(score) => onComplete(lesson.id, score, lessonXp(lesson))}
          />
        </div>
      )}
      <span className="sr-only">{`Part of ${academy.title}`}</span>
    </article>
  );
}

export default function AcademyHubPage() {
  const [progress, setProgress] = useState<Progress>(loadProgress);
  const [activeId, setActiveId] = useState<string>(academies[0]?.id ?? '');

  const active: Academy | undefined = useMemo(
    () => academies.find((a) => a.id === activeId) ?? academies[0],
    [activeId],
  );

  const handleComplete = useCallback(
    (lessonId: string, score: number, xp: number) => {
      setProgress((prev) => {
        const already = prev.completedLessons.includes(lessonId);
        const prevBest = prev.quizScores[lessonId] ?? 0;
        const next: Progress = {
          xp: prev.xp + (already ? 0 : xp),
          completedLessons: already ? prev.completedLessons : [...prev.completedLessons, lessonId],
          quizScores: { ...prev.quizScores, [lessonId]: Math.max(prevBest, score) },
        };
        saveProgress(next);
        return next;
      });
    },
    [],
  );

  const academyDone = (a: Academy) =>
    a.lessons.filter((l) => progress.completedLessons.includes(l.id)).length;

  return (
    <div className="mx-auto max-w-feed px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-white">SupremeAI Academies</h1>
        <p className="mt-2 text-sm text-white/60">
          Free, interactive courses on our own stack. Progress lives in your browser
          (localStorage) — no account, no tracking.
        </p>
        <p className="mt-1 font-mono text-xs text-emerald-300">XP: {progress.xp}</p>
      </header>

      <nav className="mb-6 flex flex-wrap gap-2" aria-label="Academy selector">
        {academies.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => setActiveId(a.id)}
            className={`rounded-lg border px-4 py-2 text-left transition ${
              a.id === active?.id
                ? 'border-purple-400/50 bg-purple-400/10'
                : 'border-white/10 bg-white/[0.03] hover:border-white/25'
            }`}
            aria-pressed={a.id === active?.id}
          >
            <span className="block text-sm font-medium text-white">{a.title}</span>
            <span className="block font-mono text-xs text-white/50">
              {academyDone(a)}/{a.lessons.length} lessons · {a.level}
            </span>
          </button>
        ))}
      </nav>

      {active && (
        <section className="space-y-3">
          <p className="mb-4 text-sm text-white/60">{active.tagline}</p>
          {active.lessons.map((lesson, i) => (
            <LessonCard
              key={lesson.id}
              academy={active}
              lesson={lesson}
              index={i}
              done={progress.completedLessons.includes(lesson.id)}
              bestScore={progress.quizScores[lesson.id] ?? 0}
              onComplete={handleComplete}
            />
          ))}
        </section>
      )}
    </div>
  );
}

export { AcademyHubPage };

