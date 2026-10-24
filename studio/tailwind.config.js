/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // ✅ SupremeAI Design Tokens
      colors: {
        ink: '#06070B',
        surface: '#0B0F17',
        raised: '#111722',
        text: '#F8FAFC',
        secondary: '#94A3B8',
        muted: '#64748B',
        border: 'rgba(255, 255, 255, 0.08)',
        user: {
          primary: '#A855F7',
          secondary: '#7C3AED',
        },
        admin: {
          primary: '#00F3FF',
          secondary: '#22D3EE',
        },
        semantic: {
          success: '#22C55E',
          warning: '#F59E0B',
          danger: '#F43F5E',
          info: '#38BDF8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '128': '32rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
