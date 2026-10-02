import React from "react";
import ReactDOM from "react-dom/client";

import "../tokens.css";
import { SiteEditor } from "./SiteEditor";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SiteEditor />
  </React.StrictMode>,
);
