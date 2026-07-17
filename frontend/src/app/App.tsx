import { RouterProvider } from "react-router-dom";

import { appRouter } from "./router";
import { AppProviders } from "./providers";

export function App() {
  return (
    <AppProviders>
      <RouterProvider router={appRouter} />
    </AppProviders>
  );
}
