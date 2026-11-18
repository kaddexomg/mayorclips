/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        abyss: "#060B10",
        ink: "#14242B",
        "ink-light": "#1A2F38",
        brand: "#2BF0C8",
        "brand-fg": "#060B10",
        "signal-ink": "#0B7355",
        mineral: "#F6FBF9",
        "text-muted": "#94A3B8",
        "text-main": "#E8F6F2"
      },
      fontFamily: {
        display: ["Sora", "sans-serif"],
        sans: ["'IBM Plex Sans'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        'brand-glow': '0 0 25px -5px rgba(43, 240, 200, 0.25)',
        'card-glow': '0 4px 20px -2px rgba(6, 11, 16, 0.7)',
      }
    },
  },
  plugins: [],
}
