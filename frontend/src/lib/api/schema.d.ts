export interface paths {
    "/api/v1/api-keys": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Api Keys */
        get: operations["list_api_keys_api_v1_api_keys_get"];
        put?: never;
        /** Create Api Key */
        post: operations["create_api_key_api_v1_api_keys_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/api-keys/{key_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Api Key */
        get: operations["get_api_key_api_v1_api_keys__key_uuid__get"];
        put?: never;
        post?: never;
        /** Revoke Api Key */
        delete: operations["revoke_api_key_api_v1_api_keys__key_uuid__delete"];
        options?: never;
        head?: never;
        /** Update Api Key */
        patch: operations["update_api_key_api_v1_api_keys__key_uuid__patch"];
        trace?: never;
    };
    "/api/v1/api-keys/options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Api Key Options */
        get: operations["api_key_options_api_v1_api_keys_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Auth Config */
        get: operations["auth_config_api_v1_auth_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/csrf": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Csrf Token */
        get: operations["csrf_token_api_v1_auth_csrf_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/google/callback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Google Callback */
        get: operations["google_callback_api_v1_auth_google_callback_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/google/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Google Start */
        get: operations["google_start_api_v1_auth_google_start_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/mfa/passkeys/begin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Begin Passkey Authentication */
        post: operations["begin_passkey_authentication_api_v1_auth_mfa_passkeys_begin_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/mfa/passkeys/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete Passkey Authentication */
        post: operations["complete_passkey_authentication_api_v1_auth_mfa_passkeys_complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/mfa/recovery/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Verify Recovery Code */
        post: operations["verify_recovery_code_api_v1_auth_mfa_recovery_verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/mfa/totp/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Verify Totp */
        post: operations["verify_totp_api_v1_auth_mfa_totp_verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password/forgot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Password Forgot */
        post: operations["password_forgot_api_v1_auth_password_forgot_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Password Reset */
        post: operations["password_reset_api_v1_auth_password_reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Session */
        get: operations["session_api_v1_auth_session_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/signup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Signup */
        post: operations["signup_api_v1_auth_signup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Billings */
        get: operations["list_billings_api_v1_billings_get"];
        put?: never;
        /** Create Billing */
        post: operations["create_billing_api_v1_billings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Billing */
        get: operations["get_billing_api_v1_billings__billing_uuid__get"];
        put?: never;
        post?: never;
        /** Delete Billing */
        delete: operations["delete_billing_api_v1_billings__billing_uuid__delete"];
        options?: never;
        head?: never;
        /** Update Billing */
        patch: operations["update_billing_api_v1_billings__billing_uuid__patch"];
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/attachments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Attachments */
        get: operations["list_attachments_api_v1_billings__billing_uuid__attachments_get"];
        put?: never;
        /** Upload Attachment */
        post: operations["upload_attachment_api_v1_billings__billing_uuid__attachments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/attachments/{attachment_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Attachment */
        get: operations["download_attachment_api_v1_billings__billing_uuid__attachments__attachment_uuid__get"];
        put?: never;
        post?: never;
        /** Delete Attachment */
        delete: operations["delete_attachment_api_v1_billings__billing_uuid__attachments__attachment_uuid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Bills */
        get: operations["list_bills_api_v1_billings__billing_uuid__bills_get"];
        put?: never;
        /** Create Bill */
        post: operations["create_bill_api_v1_billings__billing_uuid__bills_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Bill */
        get: operations["get_bill_api_v1_billings__billing_uuid__bills__bill_uuid__get"];
        put?: never;
        post?: never;
        /** Delete Bill */
        delete: operations["delete_bill_api_v1_billings__billing_uuid__bills__bill_uuid__delete"];
        options?: never;
        head?: never;
        /** Update Bill */
        patch: operations["update_bill_api_v1_billings__billing_uuid__bills__bill_uuid__patch"];
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/invoice": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Invoice */
        get: operations["download_invoice_api_v1_billings__billing_uuid__bills__bill_uuid__invoice_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipt-order": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Reorder Receipts */
        put: operations["reorder_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipt_order_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Receipts */
        get: operations["list_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_get"];
        put?: never;
        /** Upload Receipts */
        post: operations["upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/receipts/{receipt_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Receipt */
        get: operations["download_receipt_api_v1_billings__billing_uuid__bills__bill_uuid__receipts__receipt_uuid__get"];
        put?: never;
        post?: never;
        /** Delete Receipt */
        delete: operations["delete_receipt_api_v1_billings__billing_uuid__bills__bill_uuid__receipts__receipt_uuid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/recibo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Recibo */
        get: operations["download_recibo_api_v1_billings__billing_uuid__bills__bill_uuid__recibo_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/regenerate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Regenerate Bill */
        post: operations["regenerate_bill_api_v1_billings__billing_uuid__bills__bill_uuid__regenerate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/bills/{bill_uuid}/transitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Transition Bill */
        post: operations["transition_bill_api_v1_billings__billing_uuid__bills__bill_uuid__transitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/communications/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Communication */
        post: operations["preview_communication_api_v1_billings__billing_uuid__communications_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/communications/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Send Communication */
        post: operations["send_communication_api_v1_billings__billing_uuid__communications_send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/expenses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Expenses */
        get: operations["list_expenses_api_v1_billings__billing_uuid__expenses_get"];
        put?: never;
        /** Create Expense */
        post: operations["create_expense_api_v1_billings__billing_uuid__expenses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/expenses/{expense_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Expense */
        delete: operations["delete_expense_api_v1_billings__billing_uuid__expenses__expense_uuid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Export */
        post: operations["create_export_api_v1_billings__billing_uuid__exports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/recipients": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Recipients */
        put: operations["replace_recipients_api_v1_billings__billing_uuid__recipients_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/reply-to": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Reply To */
        put: operations["replace_reply_to_api_v1_billings__billing_uuid__reply_to_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billings/{billing_uuid}/transfer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Transfer Billing */
        post: operations["transfer_billing_api_v1_billings__billing_uuid__transfer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invites": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Pending Invites */
        get: operations["list_pending_invites_api_v1_invites_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invites/{invite_uuid}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept Invite */
        post: operations["accept_invite_api_v1_invites__invite_uuid__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invites/{invite_uuid}/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decline Invite */
        post: operations["decline_invite_api_v1_invites__invite_uuid__decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Organizations */
        get: operations["list_organizations_api_v1_organizations_get"];
        put?: never;
        /** Create Organization */
        post: operations["create_organization_api_v1_organizations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations/{organization_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Organization */
        get: operations["get_organization_api_v1_organizations__organization_uuid__get"];
        put?: never;
        post?: never;
        /** Delete Organization */
        delete: operations["delete_organization_api_v1_organizations__organization_uuid__delete"];
        options?: never;
        head?: never;
        /** Update Organization */
        patch: operations["update_organization_api_v1_organizations__organization_uuid__patch"];
        trace?: never;
    };
    "/api/v1/organizations/{organization_uuid}/billing-transfers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Transfer Billing */
        post: operations["transfer_billing_api_v1_organizations__organization_uuid__billing_transfers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations/{organization_uuid}/invites": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Invite */
        post: operations["create_invite_api_v1_organizations__organization_uuid__invites_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/organizations/{organization_uuid}/members/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Member */
        delete: operations["remove_member_api_v1_organizations__organization_uuid__members__user_id__delete"];
        options?: never;
        head?: never;
        /** Update Member Role */
        patch: operations["update_member_role_api_v1_organizations__organization_uuid__members__user_id__patch"];
        trace?: never;
    };
    "/api/v1/organizations/{organization_uuid}/mfa-policy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Mfa Policy */
        put: operations["update_mfa_policy_api_v1_organizations__organization_uuid__mfa_policy_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current Profile */
        get: operations["current_profile_api_v1_profile_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Security Summary */
        get: operations["security_summary_api_v1_security_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/change-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Change Password */
        post: operations["change_password_api_v1_security_change_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/passkeys": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Passkeys */
        get: operations["list_passkeys_api_v1_security_passkeys_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/passkeys/{passkey_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Passkey */
        delete: operations["delete_passkey_api_v1_security_passkeys__passkey_uuid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/passkeys/register/begin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Begin Passkey Registration */
        post: operations["begin_passkey_registration_api_v1_security_passkeys_register_begin_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/passkeys/register/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete Passkey Registration */
        post: operations["complete_passkey_registration_api_v1_security_passkeys_register_complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/pix": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update Pix */
        post: operations["update_pix_api_v1_security_pix_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/recovery-codes/regenerate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Regenerate Recovery Codes */
        post: operations["regenerate_recovery_codes_api_v1_security_recovery_codes_regenerate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/totp/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Totp */
        post: operations["confirm_totp_api_v1_security_totp_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/totp/disable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Disable Totp */
        post: operations["disable_totp_api_v1_security_totp_disable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/security/totp/setup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Setup Totp */
        post: operations["setup_totp_api_v1_security_totp_setup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/themes/billings/{billing_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Billing Theme */
        get: operations["get_billing_theme_api_v1_themes_billings__billing_uuid__get"];
        /** Update Billing Theme */
        put: operations["update_billing_theme_api_v1_themes_billings__billing_uuid__put"];
        post?: never;
        /** Reset Billing Theme */
        delete: operations["reset_billing_theme_api_v1_themes_billings__billing_uuid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/themes/organizations/{org_uuid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Organization Theme */
        get: operations["get_organization_theme_api_v1_themes_organizations__org_uuid__get"];
        /** Update Organization Theme */
        put: operations["update_organization_theme_api_v1_themes_organizations__org_uuid__put"];
        post?: never;
        /** Reset Organization Theme */
        delete: operations["reset_organization_theme_api_v1_themes_organizations__org_uuid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/themes/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Theme */
        post: operations["preview_theme_api_v1_themes_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/themes/user": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get User Theme */
        get: operations["get_user_theme_api_v1_themes_user_get"];
        /** Update User Theme */
        put: operations["update_user_theme_api_v1_themes_user_put"];
        post?: never;
        /** Reset User Theme */
        delete: operations["reset_user_theme_api_v1_themes_user_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AcceptedResponse */
        AcceptedResponse: {
            /**
             * Analytics Events
             * @default []
             */
            analytics_events: components["schemas"]["AnalyticsEvent"][];
            /**
             * Status
             * @default accepted
             * @constant
             */
            status: "accepted";
        };
        /** AnalyticsEvent */
        AnalyticsEvent: {
            /** Event */
            event: string;
            /** Reason */
            reason?: string | null;
            /** Via */
            via?: string | null;
        };
        /** AnalyticsSettings */
        AnalyticsSettings: {
            /**
             * Gtm Container Id
             * @default
             */
            gtm_container_id: string;
        };
        /** APIKeyCreateRequest */
        APIKeyCreateRequest: {
            /** Expires At */
            expires_at?: string | null;
            /** Grants */
            grants: components["schemas"]["APIKeyGrantRequest"][];
            /** Name */
            name: string;
            /** Scopes */
            scopes: string[];
        };
        /** APIKeyCreateResponse */
        APIKeyCreateResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Grants */
            grants: components["schemas"]["APIKeyGrantResponse"][];
            /** Hint */
            hint: string;
            /** Last Used At */
            last_used_at: string | null;
            /** Name */
            name: string;
            /** Revoked At */
            revoked_at: string | null;
            /** Scopes */
            scopes: string[];
            /** Secret */
            secret: string;
            /** Uuid */
            uuid: string;
        };
        /** APIKeyGrantRequest */
        APIKeyGrantRequest: {
            /** Resource Id */
            resource_id: string;
            /**
             * Resource Type
             * @enum {string}
             */
            resource_type: "user" | "organization";
        };
        /** APIKeyGrantResponse */
        APIKeyGrantResponse: {
            /** Available */
            available: boolean;
            /** Resource Id */
            resource_id: string | null;
            /**
             * Resource Type
             * @enum {string}
             */
            resource_type: "user" | "organization";
        };
        /** APIKeyListResponse */
        APIKeyListResponse: {
            /** Items */
            items: components["schemas"]["APIKeyResponse"][];
        };
        /** APIKeyOptionsResponse */
        APIKeyOptionsResponse: {
            /**
             * Default Expiration Days
             * @default 90
             * @constant
             */
            default_expiration_days: 90;
            /**
             * Max Expiration Days
             * @default 365
             * @constant
             */
            max_expiration_days: 365;
            /** Organizations */
            organizations: components["schemas"]["OrganizationWorkspaceOption"][];
            personal_workspace: components["schemas"]["PersonalWorkspaceOption"];
            /** Scopes */
            scopes: string[];
        };
        /** APIKeyResponse */
        APIKeyResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Grants */
            grants: components["schemas"]["APIKeyGrantResponse"][];
            /** Hint */
            hint: string;
            /** Last Used At */
            last_used_at: string | null;
            /** Name */
            name: string;
            /** Revoked At */
            revoked_at: string | null;
            /** Scopes */
            scopes: string[];
            /** Uuid */
            uuid: string;
        };
        /** APIKeyUpdateRequest */
        APIKeyUpdateRequest: {
            /** Grants */
            grants?: components["schemas"]["APIKeyGrantRequest"][] | null;
            /** Name */
            name?: string | null;
            /** Scopes */
            scopes?: string[] | null;
        };
        /** AttachmentListResponse */
        AttachmentListResponse: {
            /** Items */
            items: components["schemas"]["AttachmentResponse"][];
        };
        /** AttachmentResponse */
        AttachmentResponse: {
            /** Content Type */
            content_type: string;
            /** Created At */
            created_at?: string | null;
            /** File Size */
            file_size: number;
            /** Filename */
            filename: string;
            /** Name */
            name: string;
            /** Sort Order */
            sort_order: number;
            /** Uuid */
            uuid: string;
        };
        /** AuthConfigResponse */
        AuthConfigResponse: {
            analytics: components["schemas"]["AnalyticsSettings"];
            feature_flags: components["schemas"]["FeatureFlags"];
        };
        /** AuthenticatedResponse */
        AuthenticatedResponse: {
            bootstrap: components["schemas"]["BootstrapResponse"];
            /**
             * Status
             * @default authenticated
             * @constant
             */
            status: "authenticated";
        };
        /** AvailableTransitionResponse */
        AvailableTransitionResponse: {
            /** Label */
            label: string;
            /** Requires Confirmation */
            requires_confirmation: boolean;
            /** Style */
            style: string;
            /** Target */
            target: string;
        };
        /** BillCapabilitiesResponse */
        BillCapabilitiesResponse: {
            /** Can Delete */
            can_delete: boolean;
            /** Can Delete Receipts */
            can_delete_receipts: boolean;
            /** Can Download Invoice */
            can_download_invoice: boolean;
            /** Can Download Recibo */
            can_download_recibo: boolean;
            /** Can Edit */
            can_edit: boolean;
            /** Can Regenerate */
            can_regenerate: boolean;
            /** Can Reorder Receipts */
            can_reorder_receipts: boolean;
            /** Can Transition */
            can_transition: boolean;
            /** Can Upload Receipts */
            can_upload_receipts: boolean;
        };
        /** BillDetailResponse */
        BillDetailResponse: {
            /** Available Transitions */
            available_transitions: components["schemas"]["AvailableTransitionResponse"][];
            capabilities: components["schemas"]["BillCapabilitiesResponse"];
            /**
             * Communications
             * @default []
             */
            communications: (components["schemas"]["CommunicationHistoryResponse"] | components["schemas"]["RedactedCommunicationHistoryResponse"])[];
            /** Created At */
            created_at: string | null;
            /** Due Date */
            due_date: string | null;
            /** Has Invoice */
            has_invoice: boolean;
            /** Has Recibo */
            has_recibo: boolean;
            /** Line Items */
            line_items: components["schemas"]["BillLineItemResponse"][];
            /** Notes */
            notes: string;
            /** Pdf Render Status */
            pdf_render_status: string | null;
            receipt_upload?: components["schemas"]["ReceiptUploadSummary"];
            /**
             * Receipts
             * @default []
             */
            receipts: components["schemas"]["ReceiptResponse"][];
            /** Reference Month */
            reference_month: string;
            /** Status */
            status: string;
            /** Status Updated At */
            status_updated_at: string | null;
            /** Total Amount */
            total_amount: number;
            /** Uuid */
            uuid: string;
        };
        /** BillingCapabilitiesResponse */
        BillingCapabilitiesResponse: {
            /** Can Delete */
            can_delete: boolean;
            /** Can Edit */
            can_edit: boolean;
            /** Can Manage Bills */
            can_manage_bills: boolean;
            /** Can Transfer */
            can_transfer: boolean;
        };
        /** BillingCreateRequest */
        BillingCreateRequest: {
            /**
             * Description
             * @default
             */
            description: string;
            /** Items */
            items: components["schemas"]["BillingItemInput"][];
            /** Name */
            name: string;
            owner?: components["schemas"]["BillingOwnerRequest"];
            /**
             * Pix Key
             * @default
             */
            pix_key: string;
            /**
             * Pix Merchant City
             * @default
             */
            pix_merchant_city: string;
            /**
             * Pix Merchant Name
             * @default
             */
            pix_merchant_name: string;
            /** Recipients */
            recipients?: components["schemas"]["ContactInput"][] | null;
            /** Reply To */
            reply_to?: components["schemas"]["ContactInput"][] | null;
        };
        /** BillingItemInput */
        BillingItemInput: {
            /** Amount */
            amount: number;
            /** Description */
            description: string;
            /**
             * Item Type
             * @enum {string}
             */
            item_type: "fixed" | "variable";
        };
        /** BillingItemResponse */
        BillingItemResponse: {
            /** Amount */
            amount: number;
            /** Description */
            description: string;
            /**
             * Item Type
             * @enum {string}
             */
            item_type: "fixed" | "variable";
        };
        /** BillingListItemResponse */
        BillingListItemResponse: {
            capabilities: components["schemas"]["BillingCapabilitiesResponse"];
            current_bill?: components["schemas"]["CurrentBillResponse"] | null;
            /** Description */
            description: string;
            /** Item Count */
            item_count: number;
            /** Name */
            name: string;
            owner: components["schemas"]["BillingOwnerResponse"];
            /** Pix Needs Setup */
            pix_needs_setup: boolean;
            /** Uuid */
            uuid: string;
        };
        /** BillingListResponse */
        BillingListResponse: {
            /** Items */
            items: components["schemas"]["BillingListItemResponse"][];
            stats: components["schemas"]["BillingStatsResponse"];
            /** User Pix Incomplete */
            user_pix_incomplete: boolean;
        };
        /** BillingOwnerRequest */
        BillingOwnerRequest: {
            /**
             * Type
             * @default user
             * @enum {string}
             */
            type: "user" | "organization";
            /** Uuid */
            uuid?: string | null;
        };
        /** BillingOwnerResponse */
        BillingOwnerResponse: {
            /** Name */
            name?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "user" | "organization";
            /** Uuid */
            uuid?: string | null;
        };
        /** BillingResponse */
        BillingResponse: {
            capabilities: components["schemas"]["BillingCapabilitiesResponse"];
            /** Communication Templates */
            communication_templates: components["schemas"]["CommunicationTemplateResponse"][];
            /** Created At */
            created_at?: string | null;
            /** Description */
            description: string;
            /** Items */
            items: components["schemas"]["BillingItemResponse"][];
            /** Name */
            name: string;
            owner: components["schemas"]["BillingOwnerResponse"];
            /** Pix Key */
            pix_key: string;
            /** Pix Merchant City */
            pix_merchant_city: string;
            /** Pix Merchant Name */
            pix_merchant_name: string;
            /** Pix Needs Setup */
            pix_needs_setup: boolean;
            /** Recipients */
            recipients: (components["schemas"]["ContactReferenceResponse"] | components["schemas"]["ContactResponse"])[];
            /** Reply To */
            reply_to: (components["schemas"]["ContactReferenceResponse"] | components["schemas"]["ContactResponse"])[];
            stats: components["schemas"]["BillingStatsResponse"];
            /** Updated At */
            updated_at?: string | null;
            /** Uuid */
            uuid: string;
        };
        /** BillingStatsResponse */
        BillingStatsResponse: {
            /** Active Count */
            active_count: number;
            /** Billed Count */
            billed_count: number;
            /** Expected */
            expected: number;
            /** Net Income */
            net_income: number;
            /** Overdue */
            overdue: number;
            /** Overdue Count */
            overdue_count: number;
            /** Paid Count */
            paid_count: number;
            /** Pending */
            pending: number;
            /** Pending Count */
            pending_count: number;
            /** Received */
            received: number;
            /** Total Expenses */
            total_expenses: number;
            /** Year */
            year: number;
        };
        /** BillingTransferResponse */
        BillingTransferResponse: {
            /** Billing Uuid */
            billing_uuid: string;
            /** Organization Uuid */
            organization_uuid: string;
        };
        /** BillingUpdateRequest */
        BillingUpdateRequest: {
            /** Description */
            description?: string | null;
            /** Items */
            items?: components["schemas"]["BillingItemInput"][] | null;
            /** Name */
            name?: string | null;
            /** Pix Key */
            pix_key?: string | null;
            /** Pix Merchant City */
            pix_merchant_city?: string | null;
            /** Pix Merchant Name */
            pix_merchant_name?: string | null;
            /** Recipients */
            recipients?: components["schemas"]["ContactInput"][] | null;
            /** Reply To */
            reply_to?: components["schemas"]["ContactInput"][] | null;
        };
        /** BillLineItemRequest */
        BillLineItemRequest: {
            /** Amount */
            amount: number;
            /** Description */
            description: string;
            item_type: components["schemas"]["ItemType"];
        };
        /** BillLineItemResponse */
        BillLineItemResponse: {
            /** Amount */
            amount: number;
            /** Description */
            description: string;
            item_type: components["schemas"]["ItemType"];
            /** Sort Order */
            sort_order: number;
        };
        /** BillListResponse */
        BillListResponse: {
            /** Items */
            items: components["schemas"]["BillResponse"][];
        };
        /** BillResponse */
        BillResponse: {
            /** Available Transitions */
            available_transitions: components["schemas"]["AvailableTransitionResponse"][];
            capabilities: components["schemas"]["BillCapabilitiesResponse"];
            /** Created At */
            created_at: string | null;
            /** Due Date */
            due_date: string | null;
            /** Has Invoice */
            has_invoice: boolean;
            /** Has Recibo */
            has_recibo: boolean;
            /** Line Items */
            line_items: components["schemas"]["BillLineItemResponse"][];
            /** Notes */
            notes: string;
            /** Pdf Render Status */
            pdf_render_status: string | null;
            /** Reference Month */
            reference_month: string;
            /** Status */
            status: string;
            /** Status Updated At */
            status_updated_at: string | null;
            /** Total Amount */
            total_amount: number;
            /** Uuid */
            uuid: string;
        };
        /**
         * BillStatus
         * @enum {string}
         */
        BillStatus: "draft" | "published" | "sent" | "paid" | "cancelled" | "delayed_payment";
        /** BillTransitionRequest */
        BillTransitionRequest: {
            current_status?: components["schemas"]["BillStatus"] | null;
            target: components["schemas"]["BillStatus"];
        };
        /** BillUpdateRequest */
        BillUpdateRequest: {
            /** Due Date */
            due_date?: string | null;
            /** Line Items */
            line_items?: components["schemas"]["BillLineItemRequest"][] | null;
            /** Notes */
            notes?: string | null;
        };
        /** Body_create_bill_api_v1_billings__billing_uuid__bills_post */
        Body_create_bill_api_v1_billings__billing_uuid__bills_post: {
            /** Payload */
            payload?: string | null;
            /** Receipt Files */
            receipt_files?: string[] | null;
        };
        /** Body_upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post */
        Body_upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post: {
            /** Receipt Files */
            receipt_files: string[];
        };
        /** BootstrapAnalytics */
        BootstrapAnalytics: {
            /**
             * Events
             * @default []
             */
            events: components["schemas"]["AnalyticsEvent"][];
            /**
             * Gtm Container Id
             * @default
             */
            gtm_container_id: string;
        };
        /** BootstrapResponse */
        BootstrapResponse: {
            analytics: components["schemas"]["BootstrapAnalytics"];
            capabilities: components["schemas"]["FrontendCapabilities"];
            /** Csrf Token */
            csrf_token: string;
            feature_flags: components["schemas"]["FeatureFlags"];
            /** Pending Invite Count */
            pending_invite_count: number;
            user: components["schemas"]["BootstrapUser"];
        };
        /** BootstrapUser */
        BootstrapUser: {
            /** Email */
            email: string;
            /** Id */
            id: number;
        };
        /** CommunicationHistoryResponse */
        CommunicationHistoryResponse: {
            /** Comm Type */
            comm_type: string;
            /** Created At */
            created_at: string | null;
            /** Recipient Email */
            recipient_email: string;
            /** Recipient Name */
            recipient_name: string;
            /** Sent At */
            sent_at: string | null;
            /** Status */
            status: string;
            /** Subject */
            subject: string;
            /** Uuid */
            uuid: string;
        };
        /** CommunicationPreviewRequest */
        CommunicationPreviewRequest: {
            /**
             * Body
             * @default
             */
            body: string;
            /**
             * Subject
             * @default
             */
            subject: string;
        };
        /** CommunicationPreviewResponse */
        CommunicationPreviewResponse: {
            /** Html */
            html: string;
            /** Mild */
            mild: string[];
            /** Severe */
            severe: string[];
        };
        /** CommunicationSendRequest */
        CommunicationSendRequest: {
            /**
             * Acknowledge Warning
             * @default false
             */
            acknowledge_warning: boolean;
            /** Bill Uuid */
            bill_uuid: string;
            /** Body */
            body: string;
            /**
             * Comm Type
             * @enum {string}
             */
            comm_type: "bill_ready" | "payment_receipt";
            /** Recipient Uuids */
            recipient_uuids: string[];
            /** Save Scope */
            save_scope?: ("billing" | "owner") | null;
            /** Subject */
            subject: string;
        };
        /** CommunicationSendResponse */
        CommunicationSendResponse: {
            /** Queued Count */
            queued_count: number;
        };
        /** CommunicationTemplateResponse */
        CommunicationTemplateResponse: {
            /** Body */
            body: string;
            /**
             * Comm Type
             * @enum {string}
             */
            comm_type: "bill_ready" | "payment_receipt";
            /** Subject */
            subject: string;
        };
        /** ContactInput */
        ContactInput: {
            /** Email */
            email: string;
            /** Name */
            name: string;
        };
        /** ContactListRequest */
        ContactListRequest: {
            /** Items */
            items: components["schemas"]["ContactInput"][];
        };
        /** ContactListResponse */
        ContactListResponse: {
            /** Items */
            items: (components["schemas"]["ContactReferenceResponse"] | components["schemas"]["ContactResponse"])[];
        };
        /** ContactReferenceResponse */
        ContactReferenceResponse: {
            /** Uuid */
            uuid: string;
        };
        /** ContactResponse */
        ContactResponse: {
            /** Email */
            email: string;
            /** Name */
            name: string;
            /** Uuid */
            uuid: string;
        };
        /** CSRFResponse */
        CSRFResponse: {
            /** Csrf Token */
            csrf_token: string;
        };
        /** CurrentBillResponse */
        CurrentBillResponse: {
            /** Due Date */
            due_date?: string | null;
            /** Reference Month */
            reference_month: string;
            /** Status */
            status: string;
            /** Total Amount */
            total_amount: number;
        };
        /** CurrentProfileResponse */
        CurrentProfileResponse: {
            /** Email */
            email: string;
        };
        /** ExpenseCreateRequest */
        ExpenseCreateRequest: {
            /** Amount */
            amount: number;
            /**
             * Category
             * @enum {string}
             */
            category: "iptu" | "condominio" | "manutencao" | "seguro" | "outros";
            /** Description */
            description: string;
            /**
             * Incurred On
             * Format: date
             */
            incurred_on: string;
        };
        /** ExpenseListResponse */
        ExpenseListResponse: {
            /** Items */
            items: components["schemas"]["ExpenseResponse"][];
        };
        /** ExpenseResponse */
        ExpenseResponse: {
            /** Amount */
            amount: number;
            /**
             * Category
             * @enum {string}
             */
            category: "iptu" | "condominio" | "manutencao" | "seguro" | "outros";
            /** Created At */
            created_at?: string | null;
            /** Description */
            description: string;
            /**
             * Incurred On
             * Format: date
             */
            incurred_on: string;
            /** Uuid */
            uuid: string;
        };
        /** ExportCreateRequest */
        ExportCreateRequest: {
            /**
             * Format
             * @default csv
             * @enum {string}
             */
            format: "csv" | "xlsx";
        };
        /** ExportCreateResponse */
        ExportCreateResponse: {
            /**
             * Format
             * @enum {string}
             */
            format: "csv" | "xlsx";
            /**
             * Status
             * @default queued
             * @constant
             */
            status: "queued";
        };
        /** FeatureFlags */
        FeatureFlags: {
            /**
             * Google Auth
             * @default false
             */
            google_auth: boolean;
            /**
             * Turnstile
             * @default false
             */
            turnstile: boolean;
            /**
             * Turnstile Site Key
             * @default
             */
            turnstile_site_key: string;
        };
        /** FrontendCapabilities */
        FrontendCapabilities: {
            /** Mfa Setup Required */
            mfa_setup_required: boolean;
            /** Scopes */
            scopes: string[];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** InviteAcceptResponse */
        InviteAcceptResponse: {
            /** Mfa Setup Required */
            mfa_setup_required: boolean;
            /** Organization Uuid */
            organization_uuid: string;
            /**
             * Status
             * @default accepted
             * @constant
             */
            status: "accepted";
        };
        /** InviteDeclineResponse */
        InviteDeclineResponse: {
            /** Organization Uuid */
            organization_uuid: string;
            /**
             * Status
             * @default declined
             * @constant
             */
            status: "declined";
        };
        /**
         * ItemType
         * @enum {string}
         */
        ItemType: "fixed" | "variable" | "extra";
        /** LoginRequest */
        LoginRequest: {
            /** Email */
            email: string;
            /** Password */
            password: string;
            /**
             * Turnstile Token
             * @default
             */
            turnstile_token: string;
        };
        /** MFACodeVerifyRequest */
        MFACodeVerifyRequest: {
            /** Challenge Id */
            challenge_id: string;
            /** Code */
            code: string;
        };
        /** MFARequiredResponse */
        MFARequiredResponse: {
            /** Challenge Id */
            challenge_id: string;
            /** Methods */
            methods: string[];
            /**
             * Status
             * @default mfa_required
             * @constant
             */
            status: "mfa_required";
        };
        /** MFAStatusResponse */
        MFAStatusResponse: {
            /** Organization Enforced */
            organization_enforced: boolean;
            /** Setup Required */
            setup_required: boolean;
        };
        /** OrganizationCapabilitiesResponse */
        OrganizationCapabilitiesResponse: {
            /** Can Create Billing */
            can_create_billing: boolean;
            /** Can Invite */
            can_invite: boolean;
            /** Can Manage */
            can_manage: boolean;
        };
        /** OrganizationCreateRequest */
        OrganizationCreateRequest: {
            /** Name */
            name: string;
        };
        /** OrganizationIntegrationDetailResponse */
        OrganizationIntegrationDetailResponse: {
            capabilities: components["schemas"]["OrganizationCapabilitiesResponse"];
            /** Created At */
            created_at: string | null;
            /**
             * Current Role
             * @enum {string}
             */
            current_role: "admin" | "manager" | "viewer";
            /** Enforce Mfa */
            enforce_mfa: boolean;
            /** Name */
            name: string;
            /** Updated At */
            updated_at: string | null;
            /** Uuid */
            uuid: string;
        };
        /** OrganizationInviteCreateRequest */
        OrganizationInviteCreateRequest: {
            /** Email */
            email: string;
            /**
             * Role
             * @default viewer
             * @enum {string}
             */
            role: "admin" | "manager" | "viewer";
        };
        /** OrganizationInviteResponse */
        OrganizationInviteResponse: {
            /** Created At */
            created_at: string | null;
            /** Invited Email */
            invited_email: string;
            /** Responded At */
            responded_at: string | null;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "manager" | "viewer";
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "accepted" | "declined";
            /** Uuid */
            uuid: string;
        };
        /** OrganizationListResponse */
        OrganizationListResponse: {
            /** Items */
            items: components["schemas"]["OrganizationResponse"][];
        };
        /** OrganizationLoginDetailResponse */
        OrganizationLoginDetailResponse: {
            capabilities: components["schemas"]["OrganizationCapabilitiesResponse"];
            /** Created At */
            created_at: string | null;
            /**
             * Current Role
             * @enum {string}
             */
            current_role: "admin" | "manager" | "viewer";
            /** Enforce Mfa */
            enforce_mfa: boolean;
            /** Invites */
            invites: components["schemas"]["OrganizationInviteResponse"][];
            /** Members */
            members: components["schemas"]["OrganizationMemberResponse"][];
            /** Name */
            name: string;
            settings: components["schemas"]["OrganizationSettingsResponse"] | null;
            /** Updated At */
            updated_at: string | null;
            /** Uuid */
            uuid: string;
        };
        /** OrganizationMemberResponse */
        OrganizationMemberResponse: {
            /** Created At */
            created_at: string | null;
            /** Email */
            email: string;
            /** Is Current User */
            is_current_user: boolean;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "manager" | "viewer";
            /** User Id */
            user_id: number;
        };
        /** OrganizationMemberUpdateRequest */
        OrganizationMemberUpdateRequest: {
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "manager" | "viewer";
        };
        /** OrganizationMFAPolicyRequest */
        OrganizationMFAPolicyRequest: {
            /** Enforce Mfa */
            enforce_mfa: boolean;
        };
        /** OrganizationMFAPolicyResponse */
        OrganizationMFAPolicyResponse: {
            /** Enforce Mfa */
            enforce_mfa: boolean;
            /** Mfa Setup Required */
            mfa_setup_required: boolean;
        };
        /** OrganizationResponse */
        OrganizationResponse: {
            capabilities: components["schemas"]["OrganizationCapabilitiesResponse"];
            /** Created At */
            created_at: string | null;
            /**
             * Current Role
             * @enum {string}
             */
            current_role: "admin" | "manager" | "viewer";
            /** Enforce Mfa */
            enforce_mfa: boolean;
            /** Name */
            name: string;
            /** Updated At */
            updated_at: string | null;
            /** Uuid */
            uuid: string;
        };
        /** OrganizationSettingsResponse */
        OrganizationSettingsResponse: {
            /** Pix Key */
            pix_key: string;
            /** Pix Merchant City */
            pix_merchant_city: string;
            /** Pix Merchant Name */
            pix_merchant_name: string;
        };
        /** OrganizationUpdateRequest */
        OrganizationUpdateRequest: {
            /** Name */
            name?: string | null;
            /** Pix Key */
            pix_key?: string | null;
            /** Pix Merchant City */
            pix_merchant_city?: string | null;
            /** Pix Merchant Name */
            pix_merchant_name?: string | null;
        };
        /** OrganizationWorkspaceOption */
        OrganizationWorkspaceOption: {
            /** Name */
            name: string;
            /** Resource Id */
            resource_id: string;
            /**
             * Resource Type
             * @default organization
             * @constant
             */
            resource_type: "organization";
        };
        /** PasskeyAuthBeginRequest */
        PasskeyAuthBeginRequest: {
            /** Challenge Id */
            challenge_id: string;
        };
        /** PasskeyAuthCompleteRequest */
        PasskeyAuthCompleteRequest: {
            /** Challenge Id */
            challenge_id: string;
            credential: components["schemas"]["WebAuthnAuthenticationCredential"];
        };
        /** PasskeyListResponse */
        PasskeyListResponse: {
            /** Items */
            items: components["schemas"]["PasskeyResponse"][];
        };
        /** PasskeyRegistrationBeginResponse */
        PasskeyRegistrationBeginResponse: {
            /** Challenge Id */
            challenge_id: string;
            options: components["schemas"]["WebAuthnRegistrationOptions"];
        };
        /** PasskeyRegistrationCompleteRequest */
        PasskeyRegistrationCompleteRequest: {
            /** Challenge Id */
            challenge_id: string;
            credential: components["schemas"]["WebAuthnRegistrationCredential"];
            /**
             * Name
             * @default Minha Passkey
             */
            name: string;
        };
        /** PasskeyResponse */
        PasskeyResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Last Used At */
            last_used_at?: string | null;
            /** Name */
            name: string;
            /** Uuid */
            uuid: string;
        };
        /** PasswordChangeRequest */
        PasswordChangeRequest: {
            /** Confirm Password */
            confirm_password: string;
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
        };
        /** PasswordForgotRequest */
        PasswordForgotRequest: {
            /** Email */
            email: string;
            /**
             * Turnstile Token
             * @default
             */
            turnstile_token: string;
        };
        /** PasswordResetRequest */
        PasswordResetRequest: {
            /** Confirm Password */
            confirm_password: string;
            /** Password */
            password: string;
            /** Token */
            token: string;
        };
        /** PendingInviteIntegrationListResponse */
        PendingInviteIntegrationListResponse: {
            /** Items */
            items: components["schemas"]["PendingInviteIntegrationResponse"][];
        };
        /** PendingInviteIntegrationResponse */
        PendingInviteIntegrationResponse: {
            /** Created At */
            created_at: string | null;
            /** Enforce Mfa */
            enforce_mfa: boolean;
            /** Organization Name */
            organization_name: string;
            /** Organization Uuid */
            organization_uuid: string;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "manager" | "viewer";
            /** Uuid */
            uuid: string;
        };
        /** PendingInviteLoginListResponse */
        PendingInviteLoginListResponse: {
            /** Items */
            items: components["schemas"]["PendingInviteLoginResponse"][];
        };
        /** PendingInviteLoginResponse */
        PendingInviteLoginResponse: {
            /** Created At */
            created_at: string | null;
            /** Enforce Mfa */
            enforce_mfa: boolean;
            /** Invited By Email */
            invited_by_email: string;
            /** Organization Name */
            organization_name: string;
            /** Organization Uuid */
            organization_uuid: string;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "manager" | "viewer";
            /** Uuid */
            uuid: string;
        };
        /** PersonalWorkspaceOption */
        PersonalWorkspaceOption: {
            /**
             * Resource Id
             * @default personal
             * @constant
             */
            resource_id: "personal";
            /**
             * Resource Type
             * @default user
             * @constant
             */
            resource_type: "user";
        };
        /** PixUpdateRequest */
        PixUpdateRequest: {
            /**
             * Pix Key
             * @default
             */
            pix_key: string;
            /**
             * Pix Merchant City
             * @default
             */
            pix_merchant_city: string;
            /**
             * Pix Merchant Name
             * @default
             */
            pix_merchant_name: string;
        };
        /** PixUpdateResponse */
        PixUpdateResponse: {
            profile: components["schemas"]["ProfileResponse"];
        };
        /** Problem */
        Problem: {
            /** Code */
            code: string;
            /** Detail */
            detail: string;
            /** Fields */
            fields?: {
                [key: string]: string;
            };
            /** Request Id */
            request_id: string;
            /** Status */
            status: number;
            /** Title */
            title: string;
            /** Type */
            type: string;
        };
        /** ProfileResponse */
        ProfileResponse: {
            /** Email */
            email: string;
            /**
             * Pix Key
             * @default
             */
            pix_key: string;
            /**
             * Pix Merchant City
             * @default
             */
            pix_merchant_city: string;
            /**
             * Pix Merchant Name
             * @default
             */
            pix_merchant_name: string;
        };
        /** ReceiptListResponse */
        ReceiptListResponse: {
            /** Items */
            items: components["schemas"]["ReceiptResponse"][];
        };
        /** ReceiptOrderRequest */
        ReceiptOrderRequest: {
            /** Order */
            order: string[];
        };
        /** ReceiptResponse */
        ReceiptResponse: {
            /** Content Type */
            content_type: string;
            /** Created At */
            created_at: string | null;
            /** File Size */
            file_size: number;
            /** Filename */
            filename: string;
            /** Sort Order */
            sort_order: number;
            /** Uuid */
            uuid: string;
        };
        /** ReceiptUploadResponse */
        ReceiptUploadResponse: {
            /**
             * Attached
             * @default 0
             */
            attached: number;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ReceiptResponse"][];
            /**
             * Skipped
             * @default 0
             */
            skipped: number;
            /**
             * Total Bytes
             * @default 0
             */
            total_bytes: number;
        };
        /** ReceiptUploadSummary */
        ReceiptUploadSummary: {
            /**
             * Attached
             * @default 0
             */
            attached: number;
            /**
             * Skipped
             * @default 0
             */
            skipped: number;
            /**
             * Total Bytes
             * @default 0
             */
            total_bytes: number;
        };
        /** RecoveryCodesResponse */
        RecoveryCodesResponse: {
            /** Recovery Codes */
            recovery_codes: string[];
        };
        /** RedactedCommunicationHistoryResponse */
        RedactedCommunicationHistoryResponse: {
            /** Comm Type */
            comm_type: string;
            /** Created At */
            created_at: string | null;
            /** Sent At */
            sent_at: string | null;
            /** Status */
            status: string;
            /** Uuid */
            uuid: string;
        };
        /** BillingTransferRequest */
        rentivo__api__schemas__billings__BillingTransferRequest: {
            /** Organization Uuid */
            organization_uuid: string;
        };
        /** BillingTransferRequest */
        rentivo__api__schemas__organizations__BillingTransferRequest: {
            /** Billing Uuid */
            billing_uuid: string;
        };
        /** SecuritySummaryResponse */
        SecuritySummaryResponse: {
            mfa: components["schemas"]["MFAStatusResponse"];
            /** Passkeys */
            passkeys: components["schemas"]["PasskeyResponse"][];
            profile: components["schemas"]["ProfileResponse"];
            totp: components["schemas"]["TOTPStatusResponse"];
        };
        /** SignupRequest */
        SignupRequest: {
            /** Confirm Password */
            confirm_password: string;
            /** Email */
            email: string;
            /** Password */
            password: string;
            /**
             * Turnstile Token
             * @default
             */
            turnstile_token: string;
        };
        /** ThemeCapabilitiesResponse */
        ThemeCapabilitiesResponse: {
            /** Can Edit */
            can_edit: boolean;
            /** Can Reset */
            can_reset: boolean;
        };
        /** ThemeOptionsResponse */
        ThemeOptionsResponse: {
            /**
             * Fonts
             * @default [
             *       "Montserrat",
             *       "Roboto",
             *       "Lora",
             *       "Playfair Display",
             *       "Open Sans",
             *       "Source Sans 3",
             *       "Merriweather",
             *       "Raleway",
             *       "Oswald",
             *       "Nunito"
             *     ]
             */
            fonts: ("Montserrat" | "Roboto" | "Lora" | "Playfair Display" | "Open Sans" | "Source Sans 3" | "Merriweather" | "Raleway" | "Oswald" | "Nunito")[];
        };
        /** ThemeResponse */
        ThemeResponse: {
            capabilities: components["schemas"]["ThemeCapabilitiesResponse"];
            effective: components["schemas"]["ThemeValuesResponse"];
            /**
             * Effective Source
             * @enum {string}
             */
            effective_source: "billing" | "organization" | "user" | "default";
            options: components["schemas"]["ThemeOptionsResponse"];
            /** Owner Name */
            owner_name: string;
            stored: components["schemas"]["ThemeValuesResponse"] | null;
        };
        /** ThemeUpdateRequest */
        ThemeUpdateRequest: {
            /**
             * Header Font
             * @enum {string}
             */
            header_font: "Montserrat" | "Roboto" | "Lora" | "Playfair Display" | "Open Sans" | "Source Sans 3" | "Merriweather" | "Raleway" | "Oswald" | "Nunito";
            /** Primary */
            primary: string;
            /** Primary Light */
            primary_light: string;
            /** Secondary */
            secondary: string;
            /** Secondary Dark */
            secondary_dark: string;
            /** Text Color */
            text_color: string;
            /** Text Contrast */
            text_contrast: string;
            /**
             * Text Font
             * @enum {string}
             */
            text_font: "Montserrat" | "Roboto" | "Lora" | "Playfair Display" | "Open Sans" | "Source Sans 3" | "Merriweather" | "Raleway" | "Oswald" | "Nunito";
        };
        /** ThemeValuesResponse */
        ThemeValuesResponse: {
            /**
             * Header Font
             * @enum {string}
             */
            header_font: "Montserrat" | "Roboto" | "Lora" | "Playfair Display" | "Open Sans" | "Source Sans 3" | "Merriweather" | "Raleway" | "Oswald" | "Nunito";
            /** Primary */
            primary: string;
            /** Primary Light */
            primary_light: string;
            /** Secondary */
            secondary: string;
            /** Secondary Dark */
            secondary_dark: string;
            /** Text Color */
            text_color: string;
            /** Text Contrast */
            text_contrast: string;
            /**
             * Text Font
             * @enum {string}
             */
            text_font: "Montserrat" | "Roboto" | "Lora" | "Playfair Display" | "Open Sans" | "Source Sans 3" | "Merriweather" | "Raleway" | "Oswald" | "Nunito";
        };
        /** TOTPConfirmRequest */
        TOTPConfirmRequest: {
            /** Code */
            code: string;
        };
        /** TOTPDisableRequest */
        TOTPDisableRequest: {
            /** Password */
            password: string;
        };
        /** TOTPSetupResponse */
        TOTPSetupResponse: {
            /** Provisioning Uri */
            provisioning_uri: string;
            /** Qr Code Base64 */
            qr_code_base64: string;
            /** Secret */
            secret: string;
        };
        /** TOTPStatusResponse */
        TOTPStatusResponse: {
            /** Enabled */
            enabled: boolean;
            /** Recovery Codes Remaining */
            recovery_codes_remaining: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** WebAuthnAuthenticationCredential */
        WebAuthnAuthenticationCredential: {
            /** Authenticatorattachment */
            authenticatorAttachment?: ("cross-platform" | "platform") | null;
            clientExtensionResults?: components["schemas"]["WebAuthnAuthenticationExtensions"];
            /** Id */
            id: string;
            /** Rawid */
            rawId: string;
            response: components["schemas"]["WebAuthnAuthenticatorAssertionResponse"];
            /**
             * Type
             * @constant
             */
            type: "public-key";
        };
        /** WebAuthnAuthenticationExtensions */
        WebAuthnAuthenticationExtensions: {
            /** Appid */
            appid?: boolean | null;
        };
        /** WebAuthnAuthenticationOptions */
        WebAuthnAuthenticationOptions: {
            /** Allowcredentials */
            allowCredentials: components["schemas"]["WebAuthnCredentialDescriptor"][];
            /** Challenge */
            challenge: string;
            /** Rpid */
            rpId: string;
            /** Timeout */
            timeout: number;
            /**
             * Userverification
             * @enum {string}
             */
            userVerification: "discouraged" | "preferred" | "required";
        };
        /** WebAuthnAuthenticatorAssertionResponse */
        WebAuthnAuthenticatorAssertionResponse: {
            /** Authenticatordata */
            authenticatorData: string;
            /** Clientdatajson */
            clientDataJSON: string;
            /** Signature */
            signature: string;
            /** Userhandle */
            userHandle?: string | null;
        };
        /** WebAuthnAuthenticatorAttestationResponse */
        WebAuthnAuthenticatorAttestationResponse: {
            /** Attestationobject */
            attestationObject: string;
            /** Clientdatajson */
            clientDataJSON: string;
            /** Transports */
            transports?: ("ble" | "cable" | "hybrid" | "internal" | "nfc" | "smart-card" | "usb")[] | null;
        };
        /** WebAuthnAuthenticatorSelection */
        WebAuthnAuthenticatorSelection: {
            /** Authenticatorattachment */
            authenticatorAttachment?: ("cross-platform" | "platform") | null;
            /** Requireresidentkey */
            requireResidentKey?: boolean | null;
            /** Residentkey */
            residentKey?: ("discouraged" | "preferred" | "required") | null;
            /** Userverification */
            userVerification?: ("discouraged" | "preferred" | "required") | null;
        };
        /** WebAuthnCredentialDescriptor */
        WebAuthnCredentialDescriptor: {
            /** Id */
            id: string;
            /** Transports */
            transports?: ("ble" | "cable" | "hybrid" | "internal" | "nfc" | "smart-card" | "usb")[] | null;
            /**
             * Type
             * @constant
             */
            type: "public-key";
        };
        /** WebAuthnCredentialParameter */
        WebAuthnCredentialParameter: {
            /** Alg */
            alg: number;
            /**
             * Type
             * @constant
             */
            type: "public-key";
        };
        /** WebAuthnCredentialProperties */
        WebAuthnCredentialProperties: {
            /** Rk */
            rk?: boolean | null;
        };
        /** WebAuthnRegistrationCredential */
        WebAuthnRegistrationCredential: {
            /** Authenticatorattachment */
            authenticatorAttachment?: ("cross-platform" | "platform") | null;
            clientExtensionResults?: components["schemas"]["WebAuthnRegistrationExtensions"];
            /** Id */
            id: string;
            /** Rawid */
            rawId: string;
            response: components["schemas"]["WebAuthnAuthenticatorAttestationResponse"];
            /**
             * Type
             * @constant
             */
            type: "public-key";
        };
        /** WebAuthnRegistrationExtensions */
        WebAuthnRegistrationExtensions: {
            credProps?: components["schemas"]["WebAuthnCredentialProperties"] | null;
        };
        /** WebAuthnRegistrationOptions */
        WebAuthnRegistrationOptions: {
            /** Attestation */
            attestation?: ("direct" | "enterprise" | "indirect" | "none") | null;
            authenticatorSelection?: components["schemas"]["WebAuthnAuthenticatorSelection"] | null;
            /** Challenge */
            challenge: string;
            /**
             * Excludecredentials
             * @default []
             */
            excludeCredentials: components["schemas"]["WebAuthnCredentialDescriptor"][];
            /**
             * Hints
             * @default []
             */
            hints: ("client-device" | "hybrid" | "security-key")[];
            /**
             * Pubkeycredparams
             * @default []
             */
            pubKeyCredParams: components["schemas"]["WebAuthnCredentialParameter"][];
            rp: components["schemas"]["WebAuthnRelyingPartyEntity"];
            /** Timeout */
            timeout?: number | null;
            user: components["schemas"]["WebAuthnUserEntity"];
        };
        /** WebAuthnRelyingPartyEntity */
        WebAuthnRelyingPartyEntity: {
            /** Id */
            id?: string | null;
            /** Name */
            name: string;
        };
        /** WebAuthnUserEntity */
        WebAuthnUserEntity: {
            /** Displayname */
            displayName: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_api_keys_api_v1_api_keys_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["APIKeyListResponse"];
                };
            };
        };
    };
    create_api_key_api_v1_api_keys_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["APIKeyCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["APIKeyCreateResponse"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_api_key_api_v1_api_keys__key_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["APIKeyResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_api_key_api_v1_api_keys__key_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_api_key_api_v1_api_keys__key_uuid__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["APIKeyUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["APIKeyResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
        };
    };
    api_key_options_api_v1_api_keys_options_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["APIKeyOptionsResponse"];
                };
            };
        };
    };
    auth_config_api_v1_auth_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthConfigResponse"];
                };
            };
        };
    };
    csrf_token_api_v1_auth_csrf_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CSRFResponse"];
                };
            };
        };
    };
    google_callback_api_v1_auth_google_callback_get: {
        parameters: {
            query?: {
                code?: string;
                error?: string;
                state?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
            /** @description Accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MFARequiredResponse"];
                };
            };
            /** @description Redirecionamento para navegação direta */
            302: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    google_start_api_v1_auth_google_start_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            302: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
            /** @description Accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MFARequiredResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    begin_passkey_authentication_api_v1_auth_mfa_passkeys_begin_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasskeyAuthBeginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WebAuthnAuthenticationOptions"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    complete_passkey_authentication_api_v1_auth_mfa_passkeys_complete_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasskeyAuthCompleteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    verify_recovery_code_api_v1_auth_mfa_recovery_verify_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MFACodeVerifyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    verify_totp_api_v1_auth_mfa_totp_verify_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MFACodeVerifyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    password_forgot_api_v1_auth_password_forgot_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordForgotRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcceptedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    password_reset_api_v1_auth_password_reset_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordResetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    session_api_v1_auth_session_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
        };
    };
    signup_api_v1_auth_signup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthenticatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_billings_api_v1_billings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingListResponse"];
                };
            };
        };
    };
    create_billing_api_v1_billings_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillingCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_billing_api_v1_billings__billing_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_billing_api_v1_billings__billing_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_billing_api_v1_billings__billing_uuid__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillingUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_attachments_api_v1_billings__billing_uuid__attachments_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttachmentListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_attachment_api_v1_billings__billing_uuid__attachments_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** Format: binary */
                    file: Blob;
                    /** @default  */
                    name?: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttachmentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_attachment_api_v1_billings__billing_uuid__attachments__attachment_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                attachment_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Attachment content */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": Blob;
                    "image/jpeg": Blob;
                    "image/png": Blob;
                };
            };
            /** @description Temporary storage redirect */
            302: {
                headers: {
                    /** @description Signed attachment URL */
                    Location?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_attachment_api_v1_billings__billing_uuid__attachments__attachment_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                attachment_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_bills_api_v1_billings__billing_uuid__bills_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillListResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_bill_api_v1_billings__billing_uuid__bills_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "multipart/form-data": components["schemas"]["Body_create_bill_api_v1_billings__billing_uuid__bills_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillDetailResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_bill_api_v1_billings__billing_uuid__bills__bill_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillDetailResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_bill_api_v1_billings__billing_uuid__bills__bill_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_bill_api_v1_billings__billing_uuid__bills__bill_uuid__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillDetailResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_invoice_api_v1_billings__billing_uuid__bills__bill_uuid__invoice_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reorder_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipt_order_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReceiptOrderRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReceiptListResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReceiptListResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_receipts_api_v1_billings__billing_uuid__bills__bill_uuid__receipts_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReceiptUploadResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_receipt_api_v1_billings__billing_uuid__bills__bill_uuid__receipts__receipt_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
                receipt_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_receipt_api_v1_billings__billing_uuid__bills__bill_uuid__receipts__receipt_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
                receipt_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_recibo_api_v1_billings__billing_uuid__bills__bill_uuid__recibo_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    regenerate_bill_api_v1_billings__billing_uuid__bills__bill_uuid__regenerate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    transition_bill_api_v1_billings__billing_uuid__bills__bill_uuid__transitions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_uuid: string;
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillTransitionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillDetailResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preview_communication_api_v1_billings__billing_uuid__communications_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CommunicationPreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommunicationPreviewResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_communication_api_v1_billings__billing_uuid__communications_send_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CommunicationSendRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommunicationSendResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_expenses_api_v1_billings__billing_uuid__expenses_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExpenseListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_expense_api_v1_billings__billing_uuid__expenses_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExpenseResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_expense_api_v1_billings__billing_uuid__expenses__expense_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
                expense_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_export_api_v1_billings__billing_uuid__exports_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExportCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replace_recipients_api_v1_billings__billing_uuid__recipients_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContactListRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContactListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replace_reply_to_api_v1_billings__billing_uuid__reply_to_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContactListRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContactListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    transfer_billing_api_v1_billings__billing_uuid__transfer_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["rentivo__api__schemas__billings__BillingTransferRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    list_pending_invites_api_v1_invites_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PendingInviteLoginListResponse"] | components["schemas"]["PendingInviteIntegrationListResponse"];
                };
            };
        };
    };
    accept_invite_api_v1_invites__invite_uuid__accept_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                invite_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InviteAcceptResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decline_invite_api_v1_invites__invite_uuid__decline_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                invite_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InviteDeclineResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_organizations_api_v1_organizations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationListResponse"];
                };
            };
        };
    };
    create_organization_api_v1_organizations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationResponse"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
        };
    };
    get_organization_api_v1_organizations__organization_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationLoginDetailResponse"] | components["schemas"]["OrganizationIntegrationDetailResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_organization_api_v1_organizations__organization_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_organization_api_v1_organizations__organization_uuid__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationLoginDetailResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
        };
    };
    transfer_billing_api_v1_organizations__organization_uuid__billing_transfers_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["rentivo__api__schemas__organizations__BillingTransferRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingTransferResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_invite_api_v1_organizations__organization_uuid__invites_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationInviteCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationInviteResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_member_api_v1_organizations__organization_uuid__members__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
                user_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_member_role_api_v1_organizations__organization_uuid__members__user_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
                user_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationMemberUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationMemberResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_mfa_policy_api_v1_organizations__organization_uuid__mfa_policy_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationMFAPolicyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrganizationMFAPolicyResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Problem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    current_profile_api_v1_profile_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrentProfileResponse"];
                };
            };
        };
    };
    security_summary_api_v1_security_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SecuritySummaryResponse"];
                };
            };
        };
    };
    change_password_api_v1_security_change_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordChangeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_passkeys_api_v1_security_passkeys_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PasskeyListResponse"];
                };
            };
        };
    };
    delete_passkey_api_v1_security_passkeys__passkey_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                passkey_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    begin_passkey_registration_api_v1_security_passkeys_register_begin_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PasskeyRegistrationBeginResponse"];
                };
            };
        };
    };
    complete_passkey_registration_api_v1_security_passkeys_register_complete_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasskeyRegistrationCompleteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PasskeyResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_pix_api_v1_security_pix_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PixUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PixUpdateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    regenerate_recovery_codes_api_v1_security_recovery_codes_regenerate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecoveryCodesResponse"];
                };
            };
        };
    };
    confirm_totp_api_v1_security_totp_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TOTPConfirmRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecoveryCodesResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    disable_totp_api_v1_security_totp_disable_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TOTPDisableRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    setup_totp_api_v1_security_totp_setup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TOTPSetupResponse"];
                };
            };
        };
    };
    get_billing_theme_api_v1_themes_billings__billing_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ThemeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_billing_theme_api_v1_themes_billings__billing_uuid__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ThemeUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ThemeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_billing_theme_api_v1_themes_billings__billing_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                billing_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_organization_theme_api_v1_themes_organizations__org_uuid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                org_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ThemeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_organization_theme_api_v1_themes_organizations__org_uuid__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                org_uuid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ThemeUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ThemeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_organization_theme_api_v1_themes_organizations__org_uuid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                org_uuid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preview_theme_api_v1_themes_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ThemeUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": Blob;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_user_theme_api_v1_themes_user_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ThemeResponse"];
                };
            };
        };
    };
    update_user_theme_api_v1_themes_user_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ThemeUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ThemeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_user_theme_api_v1_themes_user_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
}
