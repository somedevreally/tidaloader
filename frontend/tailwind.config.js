/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#7fa650",
          light: "#a6c977",
          dark: "#5f7f3c",
        },
        secondary: {
          DEFAULT: "#6f755f",
          light: "#8a907a",
          dark: "#545a44",
        },
        background: {
          DEFAULT: "#f7f4e9",
          alt: "#ece8d9",
        },
        surface: {
          DEFAULT: "#ffffff",
          alt: "#f2f0e5",
        },
        text: {
          DEFAULT: "#3a4032",
          muted: "#6f755f",
        },
        border: {
          DEFAULT: "#d3d1c5",
          light: "#e6e4d9",
        },
      },
    },
  },
  plugins: [],
};
