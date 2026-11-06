import type { ReactNode } from "react";

type IconName =
  | "logo"
  | "image"
  | "doc"
  | "layers"
  | "back"
  | "external"
  | "chevron"
  | "close"
  | "alert"
  | "check"
  | "swap"
  | "target"
  | "print"
  | "plus"
  | "info";

const paths: Record<IconName, ReactNode> = {
  logo: (
    <>
      <path d="M12 2.5 5 13h4l-3 4.5h12L15 13h4Z" />
      <path d="M12 17.5V21M5 21h14" />
    </>
  ),
  image: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="1.5" />
      <path d="m4 16.5 4.5-4.5 4 4 2.5-2.5 5 5" />
      <circle cx="15.5" cy="9" r="1.4" />
    </>
  ),
  doc: (
    <>
      <path d="M6 3.5h8l4 4v13H6Z" />
      <path d="M14 3.5v4h4M9 12h6M9 15.5h6" />
    </>
  ),
  layers: (
    <>
      <path d="m12 4 8.5 4.5L12 13 3.5 8.5Z" />
      <path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5" />
    </>
  ),
  back: <path d="M15 5 8 12l7 7" />,
  external: (
    <>
      <path d="M14 4h6v6M20 4l-9 9" />
      <path d="M18 14v6H4V6h6" />
    </>
  ),
  chevron: <path d="m9 6 6 6-6 6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  alert: (
    <>
      <path d="M12 3.5 2.5 20h19Z" />
      <path d="M12 10v4.5M12 17.3v.2" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  swap: <path d="m9 7-5 5 5 5M15 7l5 5-5 5" />,
  target: (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
    </>
  ),
  print: (
    <>
      <path d="M7 8V3.5h10V8" />
      <rect x="3.5" y="8" width="17" height="8.5" rx="1" />
      <path d="M7 14h10v6.5H7Z" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.8v.2" />
    </>
  ),
};

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export const EXPERIMENTAL = "Resultado experimental de triagem · não constitui prova nem auto de infração";

export function SimBadge({ show }: { show: boolean }) {
  return show ? (
    <span className="sim-badge" title="Dados simulados para demonstração; não representam autorizações reais">
      SIMULAÇÃO
    </span>
  ) : null;
}

export function ExperimentalSeal({ compact }: { compact?: boolean }) {
  return (
    <span className={compact ? "seal compact" : "seal"}>
      <Icon name="info" size={14} />
      {EXPERIMENTAL}
    </span>
  );
}

export function Loading({ label = "Carregando dados…" }: { label?: string }) {
  return (
    <div className="state" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({
  title = "Não foi possível carregar",
  message,
  retry,
  children,
}: {
  title?: string;
  message: string;
  retry?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="state error" role="alert">
      <Icon name="alert" size={22} />
      <h2>{title}</h2>
      <p>{message}</p>
      <div className="state-actions">
        {retry && (
          <button type="button" onClick={retry}>
            Tentar novamente
          </button>
        )}
        {children}
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state empty">
      <h2>{title}</h2>
      {children}
    </div>
  );
}
