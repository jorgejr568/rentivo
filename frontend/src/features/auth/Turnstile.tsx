import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

interface TurnstileApi {
  remove?: (widgetId: string) => void;
  render: (
    container: HTMLElement,
    options: {
      callback: (token: string) => void;
      "expired-callback": () => void;
      sitekey: string;
      theme: "light";
    }
  ) => string;
  reset: (widgetId: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export interface TurnstileHandle {
  reset: () => void;
}

interface TurnstileProps {
  enabled: boolean;
  onToken: (token: string) => void;
  siteKey: string;
}

export const Turnstile = forwardRef<TurnstileHandle, TurnstileProps>(
  function Turnstile({ enabled, onToken, siteKey }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const widgetIdRef = useRef<string | undefined>(undefined);

    useImperativeHandle(ref, () => ({
      reset() {
        onToken("");
        if (widgetIdRef.current && window.turnstile) {
          window.turnstile.reset(widgetIdRef.current);
        }
      }
    }));

    useEffect(() => {
      if (!enabled) {
        return;
      }

      const renderWidget = () => {
        if (!containerRef.current || !window.turnstile || widgetIdRef.current) {
          return;
        }
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          callback: onToken,
          "expired-callback": () => onToken(""),
          sitekey: siteKey,
          theme: "light"
        });
      };

      let script = document.querySelector<HTMLScriptElement>(
        "script[data-rentivo-turnstile]"
      );
      if (window.turnstile) {
        renderWidget();
      } else {
        if (!script) {
          script = document.createElement("script");
          script.async = true;
          script.dataset.rentivoTurnstile = "true";
          script.defer = true;
          script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
          document.head.append(script);
        }
        script.addEventListener("load", renderWidget);
      }

      return () => {
        script?.removeEventListener("load", renderWidget);
        if (widgetIdRef.current) {
          window.turnstile?.remove?.(widgetIdRef.current);
          widgetIdRef.current = undefined;
        }
      };
    }, [enabled, onToken, siteKey]);

    if (!enabled) {
      return null;
    }

    return (
      <div className="field" style={{ display: "flex", justifyContent: "center" }}>
        <div data-testid="turnstile" ref={containerRef} />
      </div>
    );
  }
);
