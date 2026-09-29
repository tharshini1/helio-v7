export default function Pulse({ wide = false }: { wide?: boolean }) {
  return (
    <svg className={`pulse ${wide ? "pulse-wide" : ""}`} viewBox="0 0 200 40" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 22 H50 L58 22 L64 8 L72 36 L79 4 L86 22 H120 L126 18 L132 22 H200" />
    </svg>
  );
}
