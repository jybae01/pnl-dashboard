import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  document.cookie = 'pnl_csrf=; Max-Age=0; Path=/';
  window.sessionStorage.clear();
  window.location.hash = '';
});
