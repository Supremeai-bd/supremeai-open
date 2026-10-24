// বাংলা মন্তব্য: Task-12 ghost activation — SessionDetailPage কম্পোনেন্টটি একটি
// সম্পূর্ণ Devin-স্টাইল সেশন ককপিট (SSE লগ স্ট্রিম + ফাইল ট্রি + reasoning log),
// কিন্তু কখনো route-এ mounted হয়নি। এই wrapper রাউটার থেকে :sessionId প্যারাম
// পড়ে কম্পোনেন্টে দেয় এবং back নেভিগেশন যোগ করে। ডেটা আসে ব্যাকএন্ডের প্রকৃত
// GET /api/session/{session_id}/stream এন্ডপয়েন্ট থেকে — কোনো নকল ইভেন্ট নেই।
import { useNavigate, useParams } from 'react-router-dom';
import { SessionDetailPage } from '../../components/dashboard/SessionDetailPage';

export function SessionDetailRoute() {
  const { sessionId = '' } = useParams();
  const navigate = useNavigate();

  if (!sessionId) {
    // বাংলা মন্তব্য: session id ছাড়া ককপিটে ঢোকা অর্থহীন — honest guard।
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--sa-ink-muted)]">
        No session id provided.
      </div>
    );
  }

  return <SessionDetailPage sessionId={sessionId} onBack={() => navigate(-1)} />;
}
