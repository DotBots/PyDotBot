import React from 'react';
import ReactDOM from 'react-dom/client';
import {
  createBrowserRouter,
  RouterProvider,
} from "react-router-dom";
import App from './App';

import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import 'bootstrap/dist/js/bootstrap.bundle.min';

import logger from './utils/logger';
const log = logger.child({ module: 'index' });
log.info(`Starting dotbot frontend`);

const router = createBrowserRouter([
  {
    path: import.meta.env.BASE_URL,
    element: <App />,
  },
], {
  future: {
    v7_relativeSplatPath: true,
    v7_fetcherPersist: true,
    v7_normalizeFormMethod: true,
    v7_partialHydration: true,
    v7_skipActionErrorRevalidation: true,
  },
});

const root = ReactDOM.createRoot(document.getElementById('dotbots') as HTMLElement);
root.render(
  <RouterProvider router={router} future={{ v7_startTransition: true }} />
);
