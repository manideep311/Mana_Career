import {
  Activity,
  Briefcase,
  FileText,
  FlaskConical,
  House,
  ScrollText,
  Sparkles,
  User,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** `false` while the destination route is still being built. */
  ready: boolean;
  /** Only rendered when the signed-in user is an admin. */
  adminOnly?: boolean;
}

/**
 * The primary navigation, in display order. Not-ready items still render (so the
 * shape of the app is visible) but are shown disabled with a "Soon" chip and are
 * omitted from the mobile bottom bar.
 */
export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Home", icon: House, ready: true },
  { href: "/resume", label: "Résumé", icon: ScrollText, ready: true },
  { href: "/jobs", label: "Jobs", icon: Briefcase, ready: true },
  { href: "/applications", label: "Applications", icon: FileText, ready: false },
  { href: "/assistant", label: "Mana AI", icon: Sparkles, ready: false },
  { href: "/activity", label: "Activity", icon: Activity, ready: true },
  { href: "/profile", label: "Profile", icon: User, ready: true },
  { href: "/eval", label: "Eval", icon: FlaskConical, ready: true, adminOnly: true },
];

/** Active when the current path is the item's href or a descendant of it. */
export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
