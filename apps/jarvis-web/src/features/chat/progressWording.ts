import type { AgentProgress } from '../../models/chat'

const progressPhrases: Record<AgentProgress, readonly string[]> = {
  processing: ['Working on your request', 'Thinking it through'],
  searching: ['Searching your resources', 'Looking through your information'],
  search_complete: ['Search step finished, organizing', 'Finishing the resource review'],
  computing: ['Working through the calculation', 'Analyzing the data'],
  reviewing: ['Checking the details', 'Reviewing the response'],
  composing: ['Composing an answer', 'Organizing the response'],
}

function phraseIndex(seed: string) {
  let value = 0
  for (const character of seed) value = (value * 31 + character.charCodeAt(0)) >>> 0
  return value
}

export function progressWording(state: AgentProgress, seed = 'jarvis') {
  const phrases = progressPhrases[state]
  return phrases[phraseIndex(`${seed}:${state}`) % phrases.length]
}
