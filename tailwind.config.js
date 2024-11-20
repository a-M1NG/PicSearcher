/** @type {import('tailwindcss').Config} */
module.exports = {
  mode: "jit",
  darkMode: 'class',
  content: ["./templates/**/*.{html,htm}"],
  theme: {
    screens: {
      'xs': '375px',
      'sm': '431px',
      'md': '768px',
      'lg': '1480px',
      'xl': '2440px',
      '2xl': '1536px',
    },
    extend: {
      fontFamily: {
        sans: ["HarmonyOS_Sans_SC", "sans-serif"],
        sans_light: ["HarmonyOS_Sans_SC_Light", "sans-serif"],
      },
      animation: {
        'bounce-down': 'bounce-down 0.3s ease-in-out',
      },
      keyframes: {
        'bounce-down': {
          '0%': { transform: 'translateY(0)' },
          '30%': { transform: 'translateY(-5px)' }, // 跳起来
          '100%': { transform: 'translateY(0)' }, // 掉下来
        },
      },
    },
  },
  plugins: [],
}

