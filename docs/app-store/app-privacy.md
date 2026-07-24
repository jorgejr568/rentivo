# App Store Connect — App Privacy questionnaire answers

Answers for the iOS app (bundle `br.com.rentivo.ios`). The app collects data
only through Rentivo's own API for app functionality. No third-party
analytics, ads, or crash SDKs are embedded in the iOS binary; web analytics
(Google Tag Manager) runs only on the website.

## Does the app collect data? → Yes

All items below: **Collected**, **Linked to the user's identity**,
**NOT used for tracking**, purpose **App Functionality** only.

| ASC category | ASC data type | What it actually is |
| --- | --- | --- |
| Contact Info | Email Address | Account e-mail (login, transactional e-mail) |
| Contact Info | Name | PIX merchant name on the user profile |
| Financial Info | Payment Info | PIX key used to generate charge QR codes |
| Financial Info | Other Financial Info | Rent charges, bills, expenses, receipt amounts |
| Identifiers | User ID | Internal account id tying data to the account |
| User Content | Other User Content | Tenant/recipient names and e-mails entered by the user |

## Everything else → Not collected

Location, Health & Fitness, Messages, Photos or Videos, Audio, Browsing
History, Search History, Purchases, Usage Data, Diagnostics, Sensitive Info,
Contacts, Other Data.

Notes:
- **Tracking (ATT):** answer **No** — no data is used to track users across
  other companies' apps or websites; no AdSupport/ATT prompt needed.
- The login step opens `rentivo.com.br` in an in-app browser session
  (`ASWebAuthenticationSession`). If GTM page-analytics on `/login` is ever
  considered in-scope collection, add Usage Data → Product Interaction
  (Analytics, not linked). Current declaration treats the binary itself as
  the boundary, which matches Apple's guidance for web-login flows.
- Keep this file in sync with `frontend/src/features/legal/PrivacyPolicyPage.tsx`
  whenever data practices change.
