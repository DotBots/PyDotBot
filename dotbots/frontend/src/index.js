import React from 'react';
import ReactDOM from 'react-dom/client';
import DotBots from './DotBots';

import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import 'bootstrap/dist/js/bootstrap.bundle.min';

const root = ReactDOM.createRoot(document.getElementById('dotbots'));
root.render(
  <React.StrictMode>
    <DotBots />
  </React.StrictMode>
);
