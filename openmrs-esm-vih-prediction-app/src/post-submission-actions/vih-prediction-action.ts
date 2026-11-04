import { showSnackbar } from '@openmrs/esm-framework';
import type { PostSubmissionAction } from '@openmrs/esm-form-engine-lib';

const action: PostSubmissionAction = {
  applyAction: async ({ encounters, sessionMode }) => {
    if (sessionMode === 'view') {
      return;
    }

    const encounter = encounters.find((item) => item.uuid);
    if (!encounter?.uuid) {
      throw new Error('OpenMRS n’a pas renvoyé l’UUID de la rencontre enregistrée.');
    }

    const apiUrl = new URL(
      `/openmrs/api/openmrs/encounter/${encodeURIComponent(encounter.uuid)}/predict`,
      `${window.location.protocol}//${window.location.hostname}:8000`,
    );

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = payload?.detail;
        const message =
          typeof detail === 'string'
            ? detail
            : detail?.message ?? `La prédiction a échoué (HTTP ${response.status}).`;
        showSnackbar({
          title: 'Prédiction VIH non disponible',
          subtitle: message,
          kind: 'error',
          isLowContrast: false,
        });
        return;
      }

      showSnackbar({
        title: 'Prédiction VIH enregistrée',
        subtitle: `${payload.prediction} — confiance ${(payload.confidence * 100).toFixed(1)} %`,
        kind: 'success',
        isLowContrast: true,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erreur de connexion à FastAPI.';
      showSnackbar({
        title: 'FastAPI est inaccessible',
        subtitle: message,
        kind: 'error',
        isLowContrast: false,
      });
    }
  },
};

export default action;
