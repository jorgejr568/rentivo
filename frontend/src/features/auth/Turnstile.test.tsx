import { act, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Turnstile, type TurnstileHandle } from "./Turnstile";

afterEach(() => {
  delete window.turnstile;
  document.head
    .querySelectorAll("script[data-rentivo-turnstile]")
    .forEach((script) => script.remove());
});

describe("Turnstile", () => {
  it("renders nothing when the feature is disabled", () => {
    const onToken = vi.fn();

    const { container } = render(
      <Turnstile enabled={false} onToken={onToken} siteKey="site-key" />
    );

    expect(container).toBeEmptyDOMElement();
    expect(onToken).not.toHaveBeenCalled();
  });

  it("renders, reports token changes, resets, and removes its widget", () => {
    const onToken = vi.fn();
    const reset = vi.fn();
    const remove = vi.fn();
    const renderWidget = vi.fn().mockReturnValue("widget-id");
    window.turnstile = { remove, render: renderWidget, reset };
    const ref = createRef<TurnstileHandle>();

    const view = render(
      <Turnstile enabled onToken={onToken} ref={ref} siteKey="site-key" />
    );

    const options = renderWidget.mock.calls[0][1];
    expect(screen.getByTestId("turnstile")).toBeVisible();
    expect(options.sitekey).toBe("site-key");
    act(() => options.callback("turnstile-token"));
    act(() => options["expired-callback"]());
    act(() => ref.current?.reset());

    expect(onToken.mock.calls).toEqual([
      ["turnstile-token"],
      [""],
      [""]
    ]);
    expect(reset).toHaveBeenCalledWith("widget-id");

    view.unmount();
    expect(remove).toHaveBeenCalledWith("widget-id");
  });

  it("loads the explicit API once and renders after it becomes available", () => {
    const onToken = vi.fn();
    const first = render(<Turnstile enabled onToken={onToken} siteKey="first" />);
    const second = render(<Turnstile enabled onToken={onToken} siteKey="second" />);

    const scripts = document.head.querySelectorAll<HTMLScriptElement>(
      "script[data-rentivo-turnstile]"
    );
    expect(scripts).toHaveLength(1);
    expect(scripts[0].src).toContain("turnstile/v0/api.js?render=explicit");

    const renderWidget = vi.fn().mockReturnValue("loaded-widget");
    window.turnstile = { render: renderWidget, reset: vi.fn() };
    act(() => scripts[0].dispatchEvent(new Event("load")));

    expect(renderWidget).toHaveBeenCalledTimes(2);
    act(() => scripts[0].dispatchEvent(new Event("load")));
    expect(renderWidget).toHaveBeenCalledTimes(2);
    first.unmount();
    second.unmount();
  });

  it("renders again after being disabled when the optional remove API is absent", () => {
    const renderWidget = vi
      .fn()
      .mockReturnValueOnce("first-widget")
      .mockReturnValueOnce("second-widget");
    window.turnstile = { render: renderWidget, reset: vi.fn() };
    const view = render(<Turnstile enabled onToken={vi.fn()} siteKey="site-key" />);

    view.rerender(<Turnstile enabled={false} onToken={vi.fn()} siteKey="site-key" />);
    view.rerender(<Turnstile enabled onToken={vi.fn()} siteKey="site-key" />);

    expect(renderWidget).toHaveBeenCalledTimes(2);
  });
});
