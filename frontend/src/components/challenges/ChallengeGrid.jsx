import React from 'react';
import ChallengeCard from './ChallengeCard';

export const CHALLENGES = [
  {
    id: 'dance',
    icon: '🕺',
    name: 'Dance',
    description: "Perform a short movement sequence to prove you're fully awake.",
    requirement: 'Follow and complete the movement sequence before the camera/sensor.',
  },
  {
    id: 'math',
    icon: '🧮',
    name: 'Math',
    description: 'Solve a generated arithmetic problem before the alarm stops.',
    requirement: 'Calculate and enter the correct numerical solution.',
  },
  {
    id: 'memory',
    icon: '🧠',
    name: 'Memory',
    description: 'Remember and reproduce a visual or spatial sequence.',
    requirement: 'Replicate the highlighted sequence in the exact order shown.',
  },
  {
    id: 'tongue_twister',
    icon: '👅',
    name: 'Tongue Twister',
    description: 'Speak a challenging tongue twister clearly to complete the challenge.',
    requirement: 'Recite the phrase with phonetic accuracy through your microphone.',
  },
  {
    id: 'pushups',
    icon: '💪',
    name: 'Push-ups',
    description: 'Complete the required number of push-ups to finish the challenge.',
    requirement: 'Perform full-range push-ups counted via pose estimation.',
  },
];

/**
 * ChallengeGrid component
 * Responsive radio group rendering the 5 official SmartWake challenge categories.
 *
 * @param {{
 *   selectedId: string | null,
 *   onSelect: (id: string) => void
 * }} props
 */
export default function ChallengeGrid({ selectedId, onSelect }) {
  return (
    <div
      role="radiogroup"
      aria-label="Select Wake-up Challenge Category"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      {CHALLENGES.map((challenge) => (
        <ChallengeCard
          key={challenge.id}
          challenge={challenge}
          isSelected={selectedId === challenge.id}
          onSelect={() => onSelect(challenge.id)}
        />
      ))}
    </div>
  );
}

ChallengeGrid.CHALLENGES = CHALLENGES;
