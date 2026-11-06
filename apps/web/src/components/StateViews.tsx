import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

/** 统一的页面状态视图：加载骨架、错误重试、空态引导。 */
export function LoadingBlock({ label = "正在加载…" }: { label?: string }) {
  return (
    <div className="state-view state-loading" role="status">
      <Loader2 className="spin" size={20} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBlock({ message = "加载失败", onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="state-view state-error" role="alert">
      <AlertTriangle size={20} />
      <span>{message}</span>
      {onRetry ? (
        <button className="secondary-action compact-button" onClick={onRetry} type="button">
          <RefreshCw size={14} />
          重试
        </button>
      ) : null}
    </div>
  );
}

export function EmptyBlock({
  children,
  title,
  action
}: {
  children?: ReactNode;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-view state-empty">
      <Inbox size={22} />
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}
