import '@testing-library/jest-dom';

// Suppress React 18 act() warnings caused by synchronous state updates in
// controlled inputs during userEvent.type sequences. Tests still catch real failures.
const originalError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  if (typeof args[0] === 'string' && args[0].includes('not wrapped in act')) return;
  if (typeof args[0] === 'string' && args[0].includes('requestSubmit')) return;
  originalError(...args);
};
