import { getAsyncLifecycle, defineConfigSchema } from '@openmrs/esm-framework';
import { registerPostSubmissionAction } from '@openmrs/esm-form-engine-lib';
import { configSchema } from './config-schema';
import { moduleName } from './constants';

const options = {
  featureName: 'extension',
  moduleName,
};

export const importTranslation = require.context('../translations', false, /.json$/, 'lazy');

export function startupApp() {
  defineConfigSchema(moduleName, configSchema);
  registerPostSubmissionAction({
    name: 'VihPredictionSubmissionAction',
    load: () => import('./post-submission-actions/vih-prediction-action'),
  });
}

// Root component
export const root = getAsyncLifecycle(() => import('./root.component'), options);
export const registerVihPredictionAction = getAsyncLifecycle(
  () => import('./register-action.component'),
  options,
);

// Extensions

// Modals

// Workspaces

