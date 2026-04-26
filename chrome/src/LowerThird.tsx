import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';

interface Props {
  title: string;
  subtitle: string;
  accent: string;
}

export const LowerThird: React.FC<Props> = ({title, subtitle, accent}) => {
  const frame = useCurrentFrame();

  const slideIn = interpolate(frame, [0, 14], [-600, 60], {extrapolateRight: 'clamp'});
  const slideOut = interpolate(frame, [100, 120], [0, -800], {extrapolateRight: 'clamp'});
  const x = slideIn + slideOut;
  const opacity = interpolate(frame, [0, 8, 100, 120], [0, 1, 1, 0], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{fontFamily: 'sans-serif', color: 'white'}}>
      <div
        style={{
          position: 'absolute',
          left: x,
          bottom: 100,
          padding: '24px 40px',
          background: 'rgba(15, 17, 23, 0.85)',
          borderLeft: `8px solid ${accent}`,
          borderRadius: 8,
          opacity,
        }}
      >
        <div style={{fontSize: 56, fontWeight: 800}}>{title}</div>
        {subtitle ? (
          <div style={{fontSize: 28, opacity: 0.7, marginTop: 4}}>{subtitle}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
