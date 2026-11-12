import React from "react";
import ReactDOM from "react-dom/client";

import "../tokens.css";
import { SiteEditorApp } from "./SiteEditorApp";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SiteEditorApp />
  </React.StrictMode>,
);
