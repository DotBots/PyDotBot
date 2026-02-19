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
const log = logger.child({module: 'index'});
log.info(`Starting dotbot frontend`);

const router = createBrowserRouter([
  {
    path: `/${process.env.PUBLIC_URL}/`,
    element: <App />,
  },
]);

const root = ReactDOM.createRoot(document.getElementById('dotbots'));
root.render(
  <RouterProvider router={router} />
);
