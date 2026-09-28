import {
  type Configuration,
  EventType,
  type AuthenticationResult,
  PublicClientApplication,
} from "@azure/msal-browser";
import { config } from "@/lib/config";

export const apiScopes = [`api://${config.azure.apiClientId}/access_as_user`];

export const msalConfig: Configuration = {
  auth: {
    clientId: config.azure.clientId,
    authority: `https://login.microsoftonline.com/${config.azure.tenantId}`,
    redirectUri: config.azure.redirectUri,
    postLogoutRedirectUri: `${config.azure.redirectUri}/login`,
  },
  // Session storage: tokens don't outlive the tab on shared nurse-station / OT terminals.
  cache: { cacheLocation: "sessionStorage" },
};

let instance: PublicClientApplication | null = null;
let ready: Promise<PublicClientApplication> | null = null;

/** Create, initialise and process any redirect response exactly once per page load. */
export function getMsal(): Promise<PublicClientApplication> {
  if (ready) return ready;
  instance = new PublicClientApplication(msalConfig);
  const pca = instance;
  ready = (async () => {
    await pca.initialize();
    const result = await pca.handleRedirectPromise();
    if (result?.account) pca.setActiveAccount(result.account);
    if (!pca.getActiveAccount()) {
      const [first] = pca.getAllAccounts();
      if (first) pca.setActiveAccount(first);
    }
    pca.addEventCallback((e) => {
      if (e.eventType === EventType.LOGIN_SUCCESS && e.payload) {
        pca.setActiveAccount((e.payload as AuthenticationResult).account);
      }
    });
    return pca;
  })();
  return ready;
}
