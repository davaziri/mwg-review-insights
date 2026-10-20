import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import "./index.css";
import { Layout } from "./components/Layout";
import { QualityPage } from "./pages/QualityPage";
import { SyncLogPage } from "./pages/SyncLogPage";
import { TitleAnalysisPage } from "./pages/TitleAnalysisPage";
import { TitlesPage } from "./pages/TitlesPage";
import { applyBrand } from "./theme/brand";

applyBrand();

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1 } },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <TitlesPage /> },
      { path: "/sync-log", element: <SyncLogPage /> },
      { path: "/titles/:id/analysis", element: <TitleAnalysisPage /> },
      { path: "/quality", element: <QualityPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
