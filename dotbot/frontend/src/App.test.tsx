import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./RestApp', () => ({ default: () => <div>RestApp</div> }));
vi.mock('./QrKeyApp', () => ({ default: () => <div>QrKeyApp</div> }));

import App from './App';

const renderApp = (search = '') =>
  render(
    <MemoryRouter initialEntries={[`/${search}`]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>
  );

beforeEach(() => localStorage.clear());

test('renders RestApp by default when no use_qrkey param', async () => {
  renderApp();
  await waitFor(() => expect(screen.getByText('RestApp')).toBeInTheDocument());
  expect(localStorage.getItem('use_qrkey')).toBe('false');
});

test('renders QrKeyApp when use_qrkey=true param is present', async () => {
  renderApp('?use_qrkey=true');
  await waitFor(() => expect(screen.getByText('QrKeyApp')).toBeInTheDocument());
  expect(localStorage.getItem('use_qrkey')).toBe('true');
});

test('renders RestApp when use_qrkey=false param is present', async () => {
  renderApp('?use_qrkey=false');
  await waitFor(() => expect(screen.getByText('RestApp')).toBeInTheDocument());
  expect(localStorage.getItem('use_qrkey')).toBe('false');
});

test('renders QrKeyApp when use_qrkey param is unrecognised but localStorage is true', async () => {
  localStorage.setItem('use_qrkey', 'true');
  renderApp('?use_qrkey=invalid');
  await waitFor(() => expect(screen.getByText('QrKeyApp')).toBeInTheDocument());
});

test('renders RestApp and sets localStorage false when use_qrkey param is unrecognised and localStorage is not true', async () => {
  renderApp('?use_qrkey=invalid');
  await waitFor(() => expect(screen.getByText('RestApp')).toBeInTheDocument());
  expect(localStorage.getItem('use_qrkey')).toBe('false');
});
