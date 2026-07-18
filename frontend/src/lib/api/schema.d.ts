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
        /** CSRFResponse */
        CSRFResponse: {
            /** Csrf Token */
            csrf_token: string;
        };
        /** CurrentProfileResponse */
        CurrentProfileResponse: {
            /** Email */
            email: string;
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
        /** RecoveryCodesResponse */
        RecoveryCodesResponse: {
            /** Recovery Codes */
            recovery_codes: string[];
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
}
