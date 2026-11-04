# @openmrs/esm-vih-prediction-app

Extension O3 qui lance la prédiction VIH après la sauvegarde du formulaire
`Evaluation VIH pour prediction IA`.

## Fonctionnement

- `src/index.ts` enregistre `VihPredictionSubmissionAction` dans le moteur de
  formulaires O3.
- `src/routes.json` charge l'extension discrète dans `patient-banner-tags-slot`
  pendant l'ouverture du dossier; `startupApp` enregistre l'action avant la
  soumission du formulaire.
- Après la soumission, l'action transmet l'UUID de la rencontre à FastAPI sur
  `http://<hôte-OpenMRS>:8000/openmrs/api/openmrs/encounter/{uuid}/predict`.
- Le navigateur envoie la session OpenMRS existante. Aucun jeton secret n'est
  inclus dans le schéma ou le bundle frontend. FastAPI vérifie cette session
  auprès d'OpenMRS avant de lire le dossier et d'écrire le résultat.

Le schéma à importer ou à réenregistrer est
[`vih_prediction_form.json`](vih_prediction_form.json); il référence déjà
l'action. Le schéma précédent de l'instance installée est conservé dans
`deploy/vih_prediction_form_before_action.json`.

## Construction et déploiement

```bash
npx --yes corepack@0.34.0 yarn install
npx --yes corepack@0.34.0 yarn build
```

La distribution Docker active monte `dist/`, les variantes JSON, gzip et
Brotli de l'import map et du registre de routes dans le conteneur frontend O3.
Les variantes compressées doivent toujours correspondre aux fichiers JSON :
Chrome privilégie Brotli. Après une mise à jour de l'image O3, régénérer ces
manifestes depuis la nouvelle distribution, y ajouter ce module et les remonter
avant de redémarrer le frontend.

FastAPI doit être accessible depuis le navigateur sur le port 8000. Par défaut,
les origines OpenMRS autorisées sont `http://localhost:8080` et
`http://127.0.0.1:8080`; elles peuvent être remplacées avec
`OPENMRS_FRONTEND_ORIGINS`.

## Quick start

```bash
yarn install
yarn start
```

Once started, your module will be available at:
**http://localhost:8080/openmrs/spa/extension**

## What's included

- ✅ OpenMRS 3.0 microfrontend setup
- ✅ Carbon Design System integration
- ✅ Internationalization (i18n) ready
- ✅ TypeScript configuration
- ✅ Vitest testing setup
- ✅ ESLint + Prettier

## Learn more

### OpenMRS O3 resources

- [Getting Started](https://o3-docs.openmrs.org/docs/getting-started) - Start here for O3 development
- [Creating a Frontend Module](https://o3-docs.openmrs.org/docs/frontend-modules/creating-a-frontend-module) - Step-by-step guide
- [Framework Concepts](https://o3-docs.openmrs.org/docs/framework-concepts) - Core O3 patterns

### Development guide

- [Extension System](https://o3-docs.openmrs.org/docs/extension-system) - Adding widgets and extensions
- [State Management](https://o3-docs.openmrs.org/docs/state-management) - Managing app state
- [Carbon and Styling](https://o3-docs.openmrs.org/docs/carbon-and-styling) - UI components and styling
- [Testing](https://o3-docs.openmrs.org/docs/testing) - Testing your module

### Community

- [OpenMRS Talk](https://talk.openmrs.org/) - Community forum for questions
- [OpenMRS Wiki](https://wiki.openmrs.org/display/RES/OpenMRS+3.x+Dev+Forum) - Join the developer community

## Common tasks

### Adding new routes

See the [Routing Guide](https://o3-docs.openmrs.org/docs/frontend-modules/routing) for details.



### Development commands

```bash
# Start development server
yarn start

# Build for production
yarn build

# Run tests
yarn test

# Watch tests
yarn test:watch

# Extract translations
yarn extract-translations

# Type checking
yarn typescript

# Linting
yarn lint

# Format code
yarn prettier
```

### Setting up source path aliases

If you want `@hooks/*`-style imports, three configs must agree, and the build config is the one that's easy to forget. Add matching entries to all of them:

**tsconfig.json**

```json
"paths": {
  "@hooks/*": ["./src/hooks/*"]
}
```

**vitest.config.ts** (under `test.alias`)

```ts
{ find: /^@hooks\/(.*)$/, replacement: r('./src/hooks/') + '$1' },
```

**rspack.config.js** (merged into the exported config)

```js
const path = require('path');

// ...
resolve: {
  alias: {
    '@hooks': path.resolve(__dirname, 'src/hooks/'),
  },
},
```

Without the build config entry, aliased imports pass type checking and tests but fail `yarn build`. See [openmrs-esm-form-builder](https://github.com/openmrs/openmrs-esm-form-builder) for a working example.

### Enforcing coverage thresholds

`yarn coverage` reports coverage without failing the build. To enforce minimums once your test suite has grown into them, add thresholds to the `coverage` block in `vitest.config.ts`:

```ts
coverage: {
  // ...
  thresholds: {
    statements: 80,
    branches: 80,
    functions: 80,
    lines: 80,
  },
},
```

## Installation

```bash
yarn add @openmrs/esm-vih-prediction-app
```

## Usage

[Add usage instructions here]

## Building

```bash
yarn build
```

## Testing

```bash
yarn test
```

## Troubleshooting

### `openmrs develop` crashes with `Cannot read properties of undefined (reading 'devServer')`

Ensure your build config re-exports the default OpenMRS config, for example:

```js
module.exports = require('openmrs/default-rspack-config');
```

### Yarn peer dependency warnings (dayjs, i18next, single-spa, swr, react-is, sass)

If you see missing peer dependency warnings, add the missing packages to your `devDependencies` at the versions the warnings name, then re-run `yarn install`.

---

This module was scaffolded with [`@openmrs/create-o3-app`](https://github.com/openmrs/create-o3-app). The `generator` field in `package.json` records the CLI version that produced it and is safe to remove.
