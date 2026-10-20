import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router";

import "./index.css";
import { Layout } from "./components/Layout";
import { TitleShell } from "./components/TitleShell";
import { ComparePage } from "./pages/ComparePage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { QualityPage } from "./pages/QualityPage";
import { SyncLogPage } from "./pages/SyncLogPage";
import { ThemePage } from "./pages/ThemePage";
import { TitleAnalysisPage } from "./pages/TitleAnalysisPage";
import { TitleOverviewPage } from "./pages/TitleOverviewPage";
import { TitleReviewsPage } from "./pages/TitleReviewsPage";
import { TitlesPage } from "./pages/TitlesPage";
import { applyBrand } from "./theme/brand";
import { ModeProvider } from "./theme/mode";

applyBrand();

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1 } },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <PortfolioPage /> },
      { path: "/compare", element: <ComparePage /> },
      { path: "/titles", element: <TitlesPage /> },
      {
        path: "/titles/:id",
        element: <TitleShell />,
        children: [
          { index: true, element: <TitleOverviewPage /> },
          { path: "themes/:key", element: <ThemePage /> },
          { path: "reviews", element: <TitleReviewsPage /> },
          { path: "analysis", element: <TitleAnalysisPage /> },
        ],
      },
      { path: "/sync-log", element: <SyncLogPage /> },
      { path: "/quality", element: <QualityPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ModeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ModeProvider>
  </StrictMode>,
);
