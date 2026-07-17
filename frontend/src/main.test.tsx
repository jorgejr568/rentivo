import { act, screen } from "@testing-library/react";

describe("main", () => {
  it("mounts the application into the root element", async () => {
    document.body.innerHTML = '<div id="root"></div>';

    let appRoot: Awaited<typeof import("./main")>["appRoot"];
    await act(async () => {
      ({ appRoot } = await import("./main"));
    });

    expect(await screen.findByRole("main")).toBeInTheDocument();
    act(() => appRoot.unmount());
  });
});
