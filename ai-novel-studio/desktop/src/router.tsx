import { createHashRouter } from "react-router-dom";

import { AppShell } from "@/components/layout/app-shell";
import { DashboardPage } from "@/pages/dashboard/dashboard-page";
import { NotFoundPage } from "@/pages/errors/not-found-page";
import {
  NovelEditorByIdPage,
  NovelEditorPage,
} from "@/pages/novel-editor/novel-editor-page";
import { ComingSoonPage } from "@/pages/placeholder/coming-soon-page";
import { ProjectDetailPage } from "@/pages/projects/project-detail-page";
import { ProjectsPage } from "@/pages/projects/projects-page";
import { SettingsPage } from "@/pages/settings/settings-page";

/**
 * Hash routing is used deliberately: Tauri serves the bundle from a custom
 * protocol on some platforms, where the History API cannot resolve deep links.
 */
export const router = createHashRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "projects/:projectId", element: <ProjectDetailPage /> },
      { path: "projects/:projectId/editor", element: <NovelEditorByIdPage /> },
      { path: "editor", element: <NovelEditorPage /> },
      { path: "knowledge", element: <ComingSoonPage /> },
      { path: "characters", element: <ComingSoonPage /> },
      { path: "storyboard", element: <ComingSoonPage /> },
      { path: "workflows", element: <ComingSoonPage /> },
      { path: "media", element: <ComingSoonPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);