import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { Button } from './ui/Button';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error caught by ErrorBoundary:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#f5f5f7] flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-[#ffffff] rounded-[18px] border border-[#e0e0e0] p-8 text-center">
            <div className="w-12 h-12 bg-[#f5f5f7] text-[#1d1d1f] border border-[#e0e0e0] rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertCircle className="w-5 h-5" aria-hidden="true" />
            </div>
            <h1 className="font-display text-[28px] font-semibold text-[#1d1d1f] tracking-[-0.28px] mb-2">
              Something went wrong
            </h1>
            <p className="text-[17px] text-[#333333] leading-[1.47] tracking-[-0.374px] mb-6">
              An unexpected error interrupted this view. Your session and data remain safe.
            </p>
            <div className="flex justify-center">
              <Button
                variant="primary"
                size="md"
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.location.reload();
                }}
              >
                <RotateCcw className="w-4 h-4" aria-hidden="true" />
                <span>Reload Application</span>
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
