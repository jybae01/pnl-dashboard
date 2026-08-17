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
        backgroundColor: '#ffffff',
        padding: '4px 10px',
        borderRadius: '6px',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 2px 6px rgba(0, 0, 0, 0.18)',
      }}
    >
      <img
        src={logoImg}
        alt={alt}
        aria-label={alt}
        style={{
          height: `${height}px`,
          width: 'auto',
          display: 'block',
          objectFit: 'contain',
        }}
      />
    </div>
  );
};
