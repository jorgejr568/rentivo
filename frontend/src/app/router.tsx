import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { AppShell } from "../components/AppShell";

export function createAppRouter(children: RouteObject[] = [{ element: null, path: "*" }]) {
  return createBrowserRouter([{ children, element: <AppShell /> }]);
}

export const appRouter = createAppRouter();
