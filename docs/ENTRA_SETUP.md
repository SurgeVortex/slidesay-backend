# SlideSay: Entra External ID Application Setup

> **Goal:** Get SlideSay up and running with Microsoft Entra External ID for authentication using OAuth2 (auth code flow) with social login (Google & Microsoft). This should take ~10 minutes.

---

## 1. Create or Reuse a Microsoft Entra External ID Tenant

If you already have an Entra tenant (or are using your org's B2C tenant), skip to step 2. Otherwise:

1. Go to [Microsoft Entra Portal](https://entra.microsoft.com/) (requires Microsoft account)
2. In the left sidebar, expand **External Identities** > **Overview**
3. Click **+ Create a new external tenant**, or select an existing B2C/External ID tenant from your directory list
4. Note your **Tenant ID** (from the Azure Portal > Overview > Directory (tenant) ID)

---

## 2. Register the SlideSay Application

1. In your Entra portal, open **Manage** > **Applications** > **App registrations**
2. Click **New registration** 
    - **Name:** `SlideSay` (or distinctive name)
    - **Supported account types:** *Accounts in this organizational directory only*
    - **Redirect URI:** 
        - Platform: **Single-page application (SPA)**
        - URIs:
            - `http://localhost:5173` *(for local dev)*
            - `https://app.slidesay.com` *(production)*
3. Click **Register**

---

## 3. Configure Authentication

1. In your new app, go to **Authentication**
2. **Platform configurations**: Confirm SPA is added and redirect URIs above are correct
3. **Logout URL:** *(optional, but recommended)*
    - `http://localhost:5173/logout`
    - `https://app.slidesay.com/logout`
4. **Implicit grant & hybrid flows:** *Do not enable (leave unchecked)*
5. **Allow public client flows:** Leave default
6. **Front-channel logout URL:** Optional

---

## 4. Set Up API Permissions (Scopes)

1. In **API permissions** tab:
2. Remove default **User.Read** if not needed
3. Click **+ Add a permission** > **Microsoft Graph** > **Delegated permissions**
    - Add:
        - `User.ReadWrite`
        - Custom API: `Presentations.ReadWrite` (add your own API, if defined)
4. Click **Add permissions**
5. Click **Grant admin consent** if required by flows

---

## 5. Enable Social Identity Providers

1. In the **External Identities** section, choose **All identity providers**
2. Add:
    - **Google**
    - **Microsoft Account**
3. For Google:
    - Follow prompts to enter your Google client ID/secret (create at [Google Cloud Console](https://console.cloud.google.com/apis/credentials))
    - Set redirect URI to your Entra endpoint (shown in the Entra UI)
4. For Microsoft Account:
    - Usually just enable it, no extra keys needed

---

## 6. Configure User Flows (Sign-up/Sign-in)

1. In **User flows** (under External Identities):
2. Click **+ New user flow** > **Sign up and sign in**
3. Name: `SlideSaySignIn`
4. Attributes (add those you need, e.g. email, name)
5. Click **Create**
6. Under user flow details, copy the **User flow ID**

---

## 7. Gather Values Needed for SlideSay

You will need the following for your `.env` files:

- **Client ID:** From your registered app (**Overview** tab)
- **Tenant ID:** From tenant (**Azure Portal > Overview**)
- **Authority URL:**
    - Format: `https://<tenant-name>.b2clogin.com/<tenant-id>.onmicrosoft.com/<user-flow>`,
    - Example: `https://yourtenant.b2clogin.com/yourtenant.onmicrosoft.com/SlideSaySignIn`

---

## 8. Environment Variable Mapping

### Frontend (`.env` or `.env.local` for dev)

```
VITE_AUTH_CLIENT_ID=<Client ID>
VITE_AUTH_TENANT_ID=<Tenant ID>
VITE_AUTH_AUTHORITY=<Authority URL>
VITE_AUTH_REDIRECT_URI=http://localhost:5173
```
- For production deploy, update `VITE_AUTH_REDIRECT_URI` to `https://app.slidesay.com`

### Backend (`.env`)

```
AUTH_CLIENT_ID=<Client ID>
AUTH_TENANT_ID=<Tenant ID>
AUTH_AUTHORITY=<Authority URL>
```

> **Note:** If your backend needs an app secret (not needed for SPA Authorization Code with PKCE), also add `AUTH_CLIENT_SECRET=<secret>`

---

## Notes
- It may take a few minutes for social providers to be active on new tenants.
- Always use the **Authorization Code flow with PKCE** for SPA security.
- Test logins with both Google and Microsoft Account via the hosted user flow URL found in Entra's user flow summary.
- If you get errors about missing consent, verify admin consent on all API permissions.

## Reference Links
- [Microsoft Entra External ID Docs](https://learn.microsoft.com/en-us/azure/active-directory/external-identities/)
- [Single-page application registration](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-spa-app-registration)
- [Add social identity providers](https://learn.microsoft.com/en-us/azure/active-directory/external-identities/social-identity-providers)
