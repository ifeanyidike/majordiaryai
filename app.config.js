const { withGradleProperties } = require('expo/config-plugins');

/**
 * Extends app.json with what cannot live in it.
 *
 * 1. `google-services.json` is Firebase's Android config, required for push
 *    notifications. The repository is public, so the file is gitignored and
 *    given to EAS as a secret file variable, GOOGLE_SERVICES_JSON, which EAS
 *    sets to a temporary path during the build. Locally it falls back to the
 *    copy in the project root.
 *
 * 2. Gradle memory. The template's default (2 GB heap, 512 MB metaspace) is
 *    no longer enough for this app: a release build ran Gradle's daemon out
 *    of metaspace, the bundle-packaging step threw, and the build hung rather
 *    than exiting. Set here rather than in a generated android/ folder so it
 *    survives every prebuild, on any machine and on EAS.
 */
const GRADLE_JVM_ARGS =
  '-Xmx4096m -XX:MaxMetaspaceSize=1024m -XX:+HeapDumpOnOutOfMemoryError -Dfile.encoding=UTF-8';

const withGradleMemory = (config) =>
  withGradleProperties(config, (c) => {
    c.modResults = c.modResults.filter(
      (item) => !(item.type === 'property' && item.key === 'org.gradle.jvmargs'),
    );
    c.modResults.push({ type: 'property', key: 'org.gradle.jvmargs', value: GRADLE_JVM_ARGS });
    return c;
  });

module.exports = ({ config }) =>
  withGradleMemory({
    ...config,
    android: {
      ...config.android,
      googleServicesFile: process.env.GOOGLE_SERVICES_JSON ?? './google-services.json',
    },
  });
