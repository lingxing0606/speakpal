export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        // 画布与文字：暖纸色底 + 墨色字（v2「安静的练习室」，见 docs/ui-visual.md）
        canvas: '#F6F3EE',
        paper: '#FBF9F5',
        sand: { 50: '#F3EEE5', 100: '#EBE4D7', 200: '#DED4C2', 300: '#C9BCA6' },
        ink: { DEFAULT: '#1F1B16', soft: '#4A443B', mute: '#6B6358' },
        line: '#E6E0D5',
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
          'PingFang SC',
          'Microsoft YaHei',
          'sans-serif',
        ],
        // 衬线只给数字与英文标题；中文标题仍用无衬线粗体（Windows 回落宋体太细）
        display: ['Georgia', 'Times New Roman', 'serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(41,33,20,0.04), 0 10px 30px -20px rgba(41,33,20,0.30)',
        soft: '0 1px 2px rgba(41,33,20,0.06), 0 6px 16px -10px rgba(41,33,20,0.28)',
        lift: '0 2px 6px rgba(41,33,20,0.05), 0 22px 44px -22px rgba(41,33,20,0.40)',
        dock: '0 -1px 0 rgba(41,33,20,0.04), 0 18px 48px -18px rgba(41,33,20,0.35)',
      },
      borderRadius: {
        card: '1.5rem',
      },
      keyframes: {
        'sp-rise': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'sp-shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'sp-float': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5px)' },
        },
      },
      animation: {
        rise: 'sp-rise 0.5s cubic-bezier(0.2, 0.7, 0.2, 1) both',
        shimmer: 'sp-shimmer 1.6s linear infinite',
        float: 'sp-float 4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
