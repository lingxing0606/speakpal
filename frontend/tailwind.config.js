export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        // 画布与文字
        canvas: '#F5F8F8',
        ink: { DEFAULT: '#1B2430', soft: '#475467', mute: '#6B7785' },
        line: '#E3EAE9',
        // 品牌青（主色）：语音 / 青玉
        brand: {
          50: '#EEF9F6',
          100: '#D5F1EA',
          200: '#ACE4D8',
          300: '#79D0BF',
          400: '#46B7A3',
          500: '#1F9C89',
          600: '#14806F',
          700: '#11675A',
          800: '#0F5249',
          900: '#0D423B',
        },
        // 暖珊瑚（强调色）：录音 / 关键数字
        coral: {
          50: '#FFF3EF',
          100: '#FFE2D8',
          300: '#FFB29B',
          400: '#FF8F73',
          500: '#FF6F52',
          600: '#E85436',
          700: '#C4402A',
        },
        good: '#12805F',
        warn: '#B45309',
        danger: '#C2413B',
      },
      fontFamily: {
        sans: [
          'Inter',
          'Noto Sans SC',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Microsoft YaHei',
          'sans-serif',
        ],
        display: ['Georgia', 'Times New Roman', 'Songti SC', 'serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,38,36,0.04), 0 12px 28px -18px rgba(16,38,36,0.35)',
        soft: '0 1px 2px rgba(16,38,36,0.06), 0 6px 16px -10px rgba(16,38,36,0.30)',
        lift: '0 2px 4px rgba(16,38,36,0.05), 0 18px 40px -20px rgba(16,38,36,0.45)',
      },
      borderRadius: {
        card: '1.25rem',
      },
    },
  },
  plugins: [],
}
