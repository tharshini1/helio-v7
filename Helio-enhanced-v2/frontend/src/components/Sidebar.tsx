import React from "react";
import { LayoutDashboard, CalendarClock, Stethoscope, BedDouble, ScanSearch, DoorOpen, Bot, ScrollText, Lock } from "lucide-react";
import Pulse from "./Pulse";

export type Page = "Dashboard" | "Appointments" | "Doctors" | "Beds" | "Diagnostics" | "Discharge" | "Agents" | "Audit";

interface SidebarProps {
  activePage: Page;
  onPageChange: (page: Page) => void;
  locked?: Page[];
}

export const menuItems: { label: Page; icon: React.ReactNode; group: string }[] = [
  { label: "Dashboard", icon: <LayoutDashboard size={18} />, group: "Overview" },
  { label: "Appointments", icon: <CalendarClock size={18} />, group: "Patient care" },
  { label: "Doctors", icon: <Stethoscope size={18} />, group: "Patient care" },
  { label: "Beds", icon: <BedDouble size={18} />, group: "Patient care" },
  { label: "Diagnostics", icon: <ScanSearch size={18} />, group: "Patient care" },
  { label: "Discharge", icon: <DoorOpen size={18} />, group: "Patient care" },
  { label: "Agents", icon: <Bot size={18} />, group: "Autonomy" },
  { label: "Audit", icon: <ScrollText size={18} />, group: "Autonomy" },
];

const Sidebar: React.FC<SidebarProps> = ({ activePage, onPageChange, locked = [] }) => {
  const groups = Array.from(new Set(menuItems.map((m) => m.group)));
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">H</div>
        <div>
          <h1>Helio</h1>
          <span>Hospital operations</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {groups.map((g) => (
          <div key={g} className="nav-group">
            <p className="nav-section-title">{g}</p>
            {menuItems.filter((m) => m.group === g).map((item) => (
              <button key={item.label} className={`nav-item ${activePage === item.label ? "active" : ""}`} onClick={() => onPageChange(item.label)}>
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
                {locked.includes(item.label) && <Lock size={13} className="nav-lock" />}
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="system-status">
          <span className="status-dot" />
          <div>
            <strong>System online</strong>
            <small>All agents responding</small>
          </div>
        </div>
        <Pulse />
      </div>
    </aside>
  );
};

export default Sidebar;
