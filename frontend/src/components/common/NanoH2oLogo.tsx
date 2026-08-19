import React from 'react';
import logoImg from '../../assets/nanoh2o-logo.png';

interface NanoH2oLogoProps {
  height?: number;
  alt?: string;
  className?: string;
}

export const NanoH2oLogo: React.FC<NanoH2oLogoProps> = ({
  height = 24,
  alt = 'NANOH2O Logo',
  className,
}) => {
  return (
    <div
      className={className}
      style={{
        backgroundColor: 'transparent',
        padding: 0,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <img
        src={logoImg}
        alt={alt}
        aria-label={alt}
        style={{
          height: `var(--nano-logo-height, ${height}px)`,
          width: 'auto',
          display: 'block',
          objectFit: 'contain',
        }}
      />
    </div>
  );
};
