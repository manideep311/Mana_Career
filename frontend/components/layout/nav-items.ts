import {
  Briefcase,
  FileText,
  House,
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
}

/**
 * The primary navigation, in display order. Not-ready items still render (so the
 * shape of the app is visible) but are shown disabled with a "Soon" chip and are
 * omitted from the mobile bottom bar.
 */
export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Home", icon: House, ready: true },
  { href: "/jobs", label: "Jobs", icon: Briefcase, ready: false },
  { href: "/applications", label: "Applications", icon: FileText, ready: false },
  { href: "/assistant", label: "Mana AI", icon: Sparkles, ready: false },
  { href: "/profile", label: "Profile", icon: User, ready: true },
];

/** Active when the current path is the item's href or a descendant of it. */
export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
