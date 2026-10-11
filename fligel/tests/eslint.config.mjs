export default [{
  files: ['**/*.js'],
  languageOptions: { ecmaVersion: 2023, sourceType: 'module', globals: {
    window:'readonly',document:'readonly',location:'readonly',localStorage:'readonly',fetch:'readonly',navigator:'readonly',
    console:'readonly',setTimeout:'readonly',clearTimeout:'readonly',setInterval:'readonly',clearInterval:'readonly',
    URL:'readonly',URLSearchParams:'readonly',Element:'readonly',FormData:'readonly',Blob:'readonly',Date:'readonly',
    caches:'readonly',getComputedStyle:'readonly',confirm:'readonly',alert:'readonly',history:'readonly',
    requestAnimationFrame:'readonly',Notification:'readonly',matchMedia:'readonly',sessionStorage:'readonly',
    AbortController:'readonly',FileReader:'readonly',Image:'readonly',HTMLElement:'readonly',Event:'readonly',CustomEvent:'readonly',
    atob:'readonly',btoa:'readonly',screen:'readonly',prompt:'readonly',IntersectionObserver:'readonly',
    ResizeObserver:'readonly',MutationObserver:'readonly',Intl:'readonly',performance:'readonly',queueMicrotask:'readonly',
    structuredClone:'readonly',crypto:'readonly',Node:'readonly',File:'readonly',Headers:'readonly',Response:'readonly',Request:'readonly',self:'readonly',createImageBitmap:'readonly',HTMLInputElement:'readonly',
  }},
  rules: { 'no-undef':'error', 'no-unused-vars':'off', 'no-use-before-define':'off' },
}];
