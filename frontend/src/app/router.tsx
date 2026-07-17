import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "../components/AppShell";

export const appRouter = createBrowserRouter([
  {
    element: <AppShell />,
    path: "*"
  }
]);
