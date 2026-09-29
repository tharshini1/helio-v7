import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Moon, LogOut } from "lucide-react";
import { menuItems } from "./Sidebar";
import type { Page } from "./Sidebar";

interface Props {
  open: boolean;
  onClose: () => void;
  onGo: (page: Page) => void;
  onToggleTheme: () => void;
  onLogout: () => void;
}

export default function CommandPalette({ open, onClose, onGo, onToggleTheme, onLogout }: Props) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const ref = useRef<HTMLInputElement>(null);

  const items = useMemo(() => {
    const all = [
      ...menuItems.map((m) => ({ label: `Go to ${m.label}`, icon: m.icon, run: () => onGo(m.label) })),
      { label: "Toggle dark mode", icon: <Moon size={18} />, run: onToggleTheme },
      { label: "Log out", icon: <LogOut size={18} />, run: onLogout },
    ];
    return all.filter((i) => i.label.toLowerCase().includes(q.toLowerCase()));
  }, [q, onGo, onToggleTheme, onLogout]);

  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);

  if (!open) return null;

  const close = () => {
    setQ("");
    setIdx(0);
    onClose();
  };
  const run = (i: number) => {
    items[i]?.run();
    close();
  };

  return (
    <div className="cmd-overlay" onMouseDown={close}>
      <div className="cmd" role="dialog" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="cmd-input">
          <Search size={18} />
          <input
            ref={ref}
            value={q}
            placeholder="Jump to a module or run an action"
            onChange={(e) => { setQ(e.target.value); setIdx(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, items.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
              else if (e.key === "Enter") run(idx);
              else if (e.key === "Escape") close();
            }}
          />
        </div>
        <ul>
          {items.map((it, i) => (
            <li key={it.label} className={i === idx ? "on" : ""} onMouseEnter={() => setIdx(i)} onClick={() => run(i)}>
              {it.icon}
              <span>{it.label}</span>
            </li>
          ))}
          {items.length === 0 && <li className="none">No match. Try a module name like Beds.</li>}
        </ul>
      </div>
    </div>
  );
}
