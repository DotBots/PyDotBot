import { vi } from 'vitest';

// react-dom/client and App must be mocked before the module-level side-effects
// in index.tsx run. vi.mock() calls are hoisted by vitest automatically.
vi.mock('react-dom/client', () => ({
  default: { createRoot: vi.fn(() => ({ render: vi.fn() })) },
}));

vi.mock('./App', () => ({ default: () => null }));

// Suppress bootstrap CSS / JS side-effects in jsdom
vi.mock('bootstrap/dist/css/bootstrap.css', () => ({}));
vi.mock('bootstrap-icons/font/bootstrap-icons.css', () => ({}));
vi.mock('bootstrap/dist/js/bootstrap.bundle.min', () => ({}));

import ReactDOM from 'react-dom/client';

test('mounts the app on the #dotbots DOM element', async () => {
  const div = document.createElement('div');
  div.id = 'dotbots';
  document.body.appendChild(div);

  // Reset module registry so index.tsx side-effects run fresh in this test.
  vi.resetModules();
  await import('./index');

  expect(ReactDOM.createRoot).toHaveBeenCalledWith(div);
  const mockRoot = vi.mocked(ReactDOM.createRoot).mock.results[0].value as { render: ReturnType<typeof vi.fn> };
  expect(mockRoot.render).toHaveBeenCalled();

  document.body.removeChild(div);
});
