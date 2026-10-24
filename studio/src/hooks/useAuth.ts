import { useAuthStore } from '../store/authStore';

export function useAuth() {
  const { user, status, login, logout, register, initialize } = useAuthStore();
  return {
    user,
    loading: status === 'uninitialized',
    error: null,
    signIn: login,
    signUp: register,
    signOut: async () => {
      logout();
    },
    initialize,
  };
}
