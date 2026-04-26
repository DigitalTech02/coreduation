import {Composition, registerRoot} from 'remotion';
import {Intro} from './Intro';
import {Outro} from './Outro';
import {LowerThird} from './LowerThird';

const FPS = 30;
const W = 1920;
const H = 1080;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Intro"
        component={Intro}
        durationInFrames={Math.round(2.6 * FPS)}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{
          channelName: 'CoreDuation',
          tagline: 'Engineering, explained.',
          accent: '#3FB6FF',
        }}
      />
      <Composition
        id="Outro"
        component={Outro}
        durationInFrames={Math.round(3.5 * FPS)}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{
          channelName: 'CoreDuation',
          message: 'Subscribe for more deep dives',
          accent: '#3FB6FF',
        }}
      />
      <Composition
        id="LowerThird"
        component={LowerThird}
        durationInFrames={Math.round(4.0 * FPS)}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{
          title: 'Section title',
          subtitle: '',
          accent: '#3FB6FF',
        }}
      />
    </>
  );
};

registerRoot(RemotionRoot);
