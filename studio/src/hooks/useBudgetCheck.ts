import { useState } from 'react';
import { apiClient, ApiError } from '../services/apiClient';

export const useBudgetCheck = () => {
  const [isChecking, setIsChecking] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const checkBudget = async (estimatedCost: number = 0): Promise<boolean> => {
    setIsChecking(true);
    setBudgetError(null);
    try {
      // FIX (API-contract audit): ব্যাকএন্ডে /api/admin/metrics/cost কখনোই ছিল না —
      // প্রতিটি প্রি-ফ্লাইট চেক নীরবে 404 খেত। এখন সঠিক ওয়ালেট-ভিত্তিক budget-check
      // এন্ডপয়েন্ট (billing_api.py): অপর্যাপ্ত ব্যালেন্সে 402 Payment Required রিটার্ন করে।
      await apiClient.get(`/api/billing/budget-check?estimated=${estimatedCost}`);
      setIsChecking(false);
      return true;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setIsChecking(false);
      if (err instanceof ApiError && err.status === 402) {
        setBudgetError(err.message || 'Insufficient budget for this operation.');
      } else {
        setBudgetError('Failed to verify budget.');
      }
      return false;
    }
  };

  return { checkBudget, isChecking, budgetError };
};
