import React from 'react';
import DanceChallenge from './challenges/DanceChallenge';
import MathChallenge from './challenges/MathChallenge';
import MemoryChallenge from './challenges/MemoryChallenge';
import TongueTwisterChallenge from './challenges/TongueTwisterChallenge';
import PushupChallenge from './challenges/PushupChallenge';

/**
 * ChallengeRunner component
 * Mounts the appropriate challenge UI based on the user's selected category.
 *
 * @param {{
 *   challengeCategory?: string,
 *   onComplete: () => void,
 *   onFail: () => void
 * }} props
 */
export default function ChallengeRunner({
  challengeCategory = 'math',
  onComplete,
  onFail,
}) {
  switch (challengeCategory) {
    case 'dance':
      return <DanceChallenge onComplete={onComplete} />;
    case 'memory':
      return <MemoryChallenge onComplete={onComplete} onFail={onFail} />;
    case 'tongue_twister':
      return <TongueTwisterChallenge onComplete={onComplete} />;
    case 'pushups':
      return <PushupChallenge onComplete={onComplete} onFail={onFail} />;
    case 'math':
    default:
      return <MathChallenge onComplete={onComplete} onFail={onFail} />;
  }
}
