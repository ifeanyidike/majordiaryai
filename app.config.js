/**
 * Extends app.json with the one value that must not live in it.
 *
 * `google-services.json` is Firebase's Android config, required for push
 * notifications. The repository is public, so the file is gitignored and
 * given to EAS as a secret file variable, GOOGLE_SERVICES_JSON, which EAS
 * sets to a temporary path during the build. Locally it falls back to the
 * copy in the project root.
 */
module.exports = ({ config }) => ({
  ...config,
  android: {
    ...config.android,
    googleServicesFile: process.env.GOOGLE_SERVICES_JSON ?? './google-services.json',
  },
});
