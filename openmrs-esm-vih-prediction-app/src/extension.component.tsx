import React from 'react';
import { useTranslation } from 'react-i18next';
import { Layer, Tile } from '@carbon/react';
import styles from './extension.scss';

const Extension: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div className={styles.container}>
      <Layer>
        <Tile className={styles.tile}>
          <h1 className={styles.heading}>
            {t('extensionHeading', 'Extension')}
          </h1>
          <p className={styles.content}>
            {t('extensionDescription', 'Welcome to the Extension page.')}
          </p>
        </Tile>
      </Layer>
    </div>
  );
};

export default Extension;