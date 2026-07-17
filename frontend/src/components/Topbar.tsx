import { CircleUserRound, Menu } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface TopbarProps {
  currentPath?: string;
  currentUser: { email: string };
  onLogout?: () => void;
  pendingInviteCount: number;
}

export function Topbar({ currentPath = window.location.pathname, currentUser, onLogout, pendingInviteCount }: TopbarProps) {
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const accountTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isAccountMenuOpen) {
      return;
    }

    const closeFromOutside = (event: MouseEvent) => {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setIsAccountMenuOpen(false);
      }
    };
    const closeFromEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsAccountMenuOpen(false);
        accountTriggerRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", closeFromOutside);
    document.addEventListener("keydown", closeFromEscape);

    return () => {
      document.removeEventListener("mousedown", closeFromOutside);
      document.removeEventListener("keydown", closeFromEscape);
    };
  }, [isAccountMenuOpen]);

  return (
    <nav className="topbar">
      <div className="wrapper">
        <a className="topbar-brand" href="/">
          <span className="brand__mark">R</span>
          <span>
            rent<em>ivo</em>
          </span>
        </a>
        <button
          aria-expanded={isMobileMenuOpen}
          aria-label="Menu"
          className="topbar-toggle"
          onClick={() => setIsMobileMenuOpen((isOpen) => !isOpen)}
          type="button"
        >
          <Menu aria-hidden="true" size={20} />
        </button>
        <div className={`topbar-menu${isMobileMenuOpen ? " open" : ""}`}>
          <a className={`topbar-link${currentPath.startsWith("/billings") ? " is-active" : ""}`} href="/billings/">
            Minhas Cobranças
          </a>
          <a
            className={`topbar-link${currentPath.startsWith("/organizations") ? " is-active" : ""}`}
            href="/organizations/"
          >
            Organizações
          </a>
          <div className="topbar-dropdown" ref={accountMenuRef}>
            <button
              aria-expanded={isAccountMenuOpen}
              className="topbar-link topbar-dropdown-toggle"
              onClick={() => setIsAccountMenuOpen((isOpen) => !isOpen)}
              ref={accountTriggerRef}
              type="button"
            >
              <CircleUserRound aria-hidden="true" className="topbar-icon" size={18} />
              {currentUser.email}
            </button>
            {isAccountMenuOpen ? (
              <div className="topbar-dropdown-menu">
                <a className="topbar-dropdown-item" href="/invites/">
                  Convites
                  {pendingInviteCount > 0 ? <span className="topbar-badge">{pendingInviteCount}</span> : null}
                </a>
                <a className="topbar-dropdown-item" href="/themes/user">Tema</a>
                <a className="topbar-dropdown-item" href="/security">Segurança</a>
                <div className="topbar-dropdown-divider" />
                <button className="topbar-dropdown-item topbar-dropdown-item--danger" onClick={onLogout} type="button">
                  Sair
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </nav>
  );
}
