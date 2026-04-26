import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

interface Props {
  channelName: string;
  message: string;
  accent: string;
}

export const Outro: React.FC<Props> = ({channelName, message, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, 14], [0, 1], {extrapolateRight: 'clamp'});
  const subtitleOpacity = interpolate(frame, [10, 22], [0, 1], {extrapolateRight: 'clamp'});
  const buttonScale = spring({frame: Math.max(0, frame - 18), fps, config: {damping: 10}});
  const pulse = 1 + 0.04 * Math.sin((frame - 28) * 0.4);

  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(circle at 50% 50%, #14202c 0%, #06090d 80%)',
        color: 'white',
        fontFamily: 'sans-serif',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          fontSize: 96,
          fontWeight: 800,
          opacity: titleOpacity,
        }}
      >
        Thanks for watching
      </div>
      <div
        style={{
          marginTop: 18,
          fontSize: 32,
          opacity: 0.8 * subtitleOpacity,
        }}
      >
        {message} — {channelName}
      </div>
      <div
        style={{
          marginTop: 56,
          padding: '28px 64px',
          borderRadius: 16,
          background: accent,
          color: '#0f1117',
          fontWeight: 800,
          fontSize: 44,
          transform: `scale(${buttonScale * (frame > 28 ? pulse : 1)})`,
          boxShadow: `0 16px 60px ${accent}66`,
        }}
      >
        Subscribe
      </div>
    </AbsoluteFill>
  );
};
