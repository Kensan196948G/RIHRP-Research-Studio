import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("render error", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="content">
        <div className="error-banner" role="alert">
          <span aria-hidden="true">⚠</span>
          <div>
            <div style={{ fontWeight: 600 }}>画面の表示中にエラーが発生しました。</div>
            <div className="small">{this.state.message || "不明なエラーです。"}</div>
            <button type="button" className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => window.location.reload()}>
              再読み込み
            </button>
          </div>
        </div>
      </div>
    );
  }
}
