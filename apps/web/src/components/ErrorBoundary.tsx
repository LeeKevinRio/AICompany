// 路由層錯誤邊界：Suspense 只能接住 lazy 載入錯誤，
// 路由頁同步 render 時 throw 仍會整頁白屏。這個 ErrorBoundary 會 catch 同步錯誤，
// 顯示友善訊息（重試 / 回首頁）而非白畫面。
import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('路由頁 render 發生錯誤：', error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ error: null });
  };

  private handleGoHome = () => {
    // 直接導回首頁並清狀態；用 location 而非 router，確保即使 router 狀態異常也能脫困。
    window.location.assign('/');
  };

  render() {
    if (this.state.error) {
      return (
        <div className="page">
          <div className="empty-state">
            <div className="empty-icon">⚠️</div>
            <p className="empty-title">這個頁面發生錯誤</p>
            <p>請重試，或回到首頁繼續使用。</p>
            <div
              style={{
                display: 'flex',
                gap: 'var(--space-3)',
                justifyContent: 'center',
                marginTop: 'var(--space-4)',
              }}
            >
              <button className="primary" style={{ width: 'auto' }} onClick={this.handleReset}>
                重試
              </button>
              <button className="secondary" style={{ width: 'auto' }} onClick={this.handleGoHome}>
                回首頁
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
