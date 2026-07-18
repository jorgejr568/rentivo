import { render, screen } from "@testing-library/react";

import { FieldError } from "./FieldError";

describe("FieldError", () => {
  it("renders a linked field error", () => {
    render(<FieldError id="name-error" message="Nome é obrigatório." />);

    expect(screen.getByText("Nome é obrigatório.")).toHaveAttribute("id", "name-error");
    expect(screen.getByText("Nome é obrigatório.")).toHaveAttribute("role", "alert");
  });

  it("renders nothing without a message", () => {
    const { container } = render(<FieldError id="name-error" />);

    expect(container).toBeEmptyDOMElement();
  });
});
