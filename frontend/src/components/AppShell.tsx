import type { ReactNode } from "react";

import { ToastRegion, type Toast } from "./ToastRegion";
import { Topbar } from "./Topbar";

export interface AppShellProps {
  children?: ReactNode;
  currentPath?: string;
  currentUser?: { email: string };
  onLogout?: () => void;
  pendingInviteCount?: number;
  toasts?: Toast[];
}

export function AppShell({
  children,
  currentPath,
  currentUser,
  onLogout,
  pendingInviteCount = 0,
  toasts = []
}: AppShellProps) {
  return (
    <>
      {currentUser ? (
        <Topbar
          currentPath={currentPath}
          currentUser={currentUser}
          onLogout={onLogout}
          pendingInviteCount={pendingInviteCount}
        />
      ) : null}
      <main className="wrapper main-content">
        <ToastRegion toasts={toasts} />
        {children}
      </main>
    </>
  );
}
