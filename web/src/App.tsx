import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useTheme } from "./lib/theme";
import {
  IconBolt,
  IconBook,
  IconBranch,
  IconGate,
  IconMoon,
  IconSun,
  IconTrace,
} from "./components/icons";
import ReviewScreen from "./screens/Review";
import LineageScreen from "./screens/Lineage";
import TrajectoriesScreen from "./screens/Trajectories";
import LessonsScreen from "./screens/Lessons";
import TryAgentScreen from "./screens/TryAgent";

const NAV = [
  { to: "/try", label: "Try an agent", icon: IconBolt },
  { to: "/review", label: "Promotion review", icon: IconGate },
  { to: "/lineage", label: "Lineage", icon: IconBranch },
  { to: "/trajectories", label: "Trajectories", icon: IconTrace },
  { to: "/lessons", label: "Lessons", icon: IconBook },
];

function Sidebar() {
  const { theme, toggle } = useTheme();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface px-3 py-5">
      <div className="mb-7 flex items-center gap-2.5 px-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-fg font-semibold">
          a
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">aprntc</div>
          <div className="text-[11px] text-faint leading-tight">apprentice console</div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                isActive
                  ? "bg-surface-2 font-medium text-fg"
                  : "text-muted hover:bg-surface-2 hover:text-fg"
              }`
            }
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>

      <button
        onClick={toggle}
        className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted transition hover:bg-surface-2 hover:text-fg"
      >
        {theme === "dark" ? <IconSun /> : <IconMoon />}
        {theme === "dark" ? "Light mode" : "Dark mode"}
      </button>
    </aside>
  );
}

export default function App() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">
          <Routes>
            <Route path="/" element={<Navigate to="/try" replace />} />
            <Route path="/try" element={<TryAgentScreen />} />
            <Route path="/review" element={<ReviewScreen />} />
            <Route path="/lineage" element={<LineageScreen />} />
            <Route path="/trajectories" element={<TrajectoriesScreen />} />
            <Route path="/lessons" element={<LessonsScreen />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
