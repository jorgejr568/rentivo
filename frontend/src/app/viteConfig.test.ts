// @vitest-environment node

import viteConfig from "../../vite.config";

it("proxies versioned API requests to the local FastAPI service", () => {
  expect(viteConfig).toMatchObject({
    server: {
      proxy: {
        "/api/v1": {
          changeOrigin: true,
          target: "http://127.0.0.1:8001"
        }
      }
    }
  });
});
