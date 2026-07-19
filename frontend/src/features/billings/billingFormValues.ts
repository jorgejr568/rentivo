import type { BillingFormValues } from "./BillingForm";

let initialItemSequence = 0;

export function emptyBillingValues(): BillingFormValues {
  initialItemSequence += 1;
  return {
    description: "",
    items: [{ amount: "", description: "", id: `billing-item-initial-${initialItemSequence}`, itemType: "fixed" }],
    name: "",
    ownerType: "user",
    ownerUuid: "",
    pixKey: "",
    pixMerchantCity: "",
    pixMerchantName: "",
    recipients: [],
    replyTo: []
  };
}
