// Build-time configuration sourced from Vite env vars.
// These map to the Task-12 CDK CfnOutputs and are wired at build (Task 15):
//   VITE_API_BASE_URL        <- ApiBaseUrl
//   VITE_COGNITO_DOMAIN      <- CognitoDomain
//   VITE_USER_POOL_CLIENT_ID <- UserPoolClientId
//   VITE_CLOUDFRONT_URL      <- CloudFrontUrl
// Missing values fall back to "" so importing this module never crashes;
// the real values are injected at build / available via the deployed origin.

export interface Config {
  apiBaseUrl: string;
  cognitoDomain: string;
  userPoolClientId: string;
  cloudFrontUrl: string;
}

const env = import.meta.env;

export const config: Config = {
  apiBaseUrl: env.VITE_API_BASE_URL ?? "",
  cognitoDomain: env.VITE_COGNITO_DOMAIN ?? "",
  userPoolClientId: env.VITE_USER_POOL_CLIENT_ID ?? "",
  cloudFrontUrl: env.VITE_CLOUDFRONT_URL ?? "",
};
