import "@testing-library/jest-dom/vitest";

const NativeRequest = globalThis.Request;

class CompatibleNavigationRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const compatibleInit = { ...init };
    delete compatibleInit.signal;
    super(input, compatibleInit);
  }
}

globalThis.Request = CompatibleNavigationRequest;
