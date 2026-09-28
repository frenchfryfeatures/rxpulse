export type AuthMode = "entra" | "dev";

export const config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
  authMode: (process.env.NEXT_PUBLIC_AUTH_MODE ?? "entra") as AuthMode,
  hospitalName: process.env.NEXT_PUBLIC_HOSPITAL_NAME ?? "Eye Care Hospital",
  idleTimeoutMinutes: Number(process.env.NEXT_PUBLIC_IDLE_TIMEOUT_MINUTES ?? 15),
  azure: {
    clientId: process.env.NEXT_PUBLIC_AZURE_CLIENT_ID ?? "",
    tenantId: process.env.NEXT_PUBLIC_AZURE_TENANT_ID ?? "",
    apiClientId: process.env.NEXT_PUBLIC_AZURE_API_CLIENT_ID ?? "",
    redirectUri: process.env.NEXT_PUBLIC_REDIRECT_URI ?? "http://localhost:3000",
  },
};
