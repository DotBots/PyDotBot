import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.tsx";
import { ChakraProvider, Container } from "@chakra-ui/react";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ChakraProvider>
      <Container minHeight="100vh">
        <App />
      </Container>
    </ChakraProvider>
  </React.StrictMode>,
);
