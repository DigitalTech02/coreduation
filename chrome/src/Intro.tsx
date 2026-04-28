import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

interface Props {
  channelName: string;
  tagline: string;
  accent: string;
}

export const Intro: React.FC<Props> = ({channelName, tagline, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const logoSpring = spring({frame, fps, config: {damping: 12}});
  const titleOpacity = interpolate(frame, [10, 22], [0, 1], {extrapolateRight: 'clamp'});
  const taglineOpacity = interpolate(frame, [22, 34], [0, 1], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(circle at 50% 40%, #1a1f2e 0%, #07090d 80%)',
        color: 'white',
        fontFamily: 'sans-serif',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          width: 180,
          height: 180,
          borderRadius: '50%',
          border: `4px solid ${accent}`,
          background: accent,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 72,
          fontWeight: 800,
          color: '#0f1117',
          transform: `scale(${logoSpring})`,
          boxShadow: `0 0 80px ${accent}55`,
        }}
      >
        DT2
      </div>
      <div
        style={{
          marginTop: 40,
          fontSize: 88,
          fontWeight: 700,
          opacity: titleOpacity,
        }}
      >
        {channelName}
      </div>
      <div
        style={{
          marginTop: 12,
          fontSize: 32,
          opacity: 0.7 * taglineOpacity,
        }}
      >
        {tagline}
      </div>
    </AbsoluteFill>
  );
};
