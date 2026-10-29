<script setup>
// 场景线性图标：跟青玉绿配色走，不用彩色 emoji（emoji 在不同系统上还会换样子）
defineProps({
  name: { type: String, default: '' },
  size: { type: Number, default: 22 },
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'briefcase'">
      <rect x="3" y="7.5" width="18" height="12" rx="2.5" />
      <path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5" />
      <path d="M3 12.5h18" />
    </template>
    <template v-else-if="name === 'coffee'">
      <path d="M4 9h12v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4Z" />
      <path d="M16 10h1.8a2.2 2.2 0 0 1 0 4.4H16" />
      <path d="M7.5 5.5c0 .9.9.9.9 1.8M11.5 5.5c0 .9.9.9.9 1.8" />
    </template>
    <template v-else-if="name === 'book'">
      <path d="M4 4.8A2.3 2.3 0 0 1 6.3 2.5H11v19H6.3A2.3 2.3 0 0 1 4 19.2Z" />
      <path d="M20 4.8a2.3 2.3 0 0 0-2.3-2.3H13v19h4.7A2.3 2.3 0 0 0 20 19.2Z" />
    </template>
    <template v-else-if="name === 'hotel'">
      <path d="M2.5 4v15.5" />
      <path d="M2.5 8.5h17a2 2 0 0 1 2 2V19.5" />
      <path d="M2.5 17h19" />
      <path d="M6.5 8.5v8.5" />
    </template>
    <template v-else-if="name === 'plane'">
      <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2a1 1 0 0 0-1.1.5l-.3.5a1 1 0 0 0 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3a1 1 0 0 0 1.3.3l.4-.3a1 1 0 0 0 .6-1.1Z" />
    </template>
    <template v-else-if="name === 'utensils'">
      <path d="M5 3v6a2 2 0 0 0 4 0V3" />
      <path d="M7 9v12" />
      <path d="M17.5 3v18" />
      <path d="M14.5 3c0 4 1.2 6 3 6" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v8M8 12h8" />
    </template>
  </svg>
</template>
