import { ArrowRight, FileSearch, Mail, PenTool, Telescope } from 'lucide-react'
import { Composer } from '../components/Composer'
import { JarvisMark } from '../components/JarvisMark'

const suggestions = [
  { icon: FileSearch, text: 'Find my recent research notes' },
  { icon: Mail, text: 'Catch me up on an email thread' },
  { icon: Telescope, text: 'Research a topic and compare sources' },
  { icon: PenTool, text: 'Help me create a project brief' },
]

export function HomePage({ onStart }: { onStart: (prompt: string) => void }) {
  return <main className="home-page"><div className="home-inner"><div className="home-intro"><span className="home-mark" aria-hidden="true"><JarvisMark size={28} /></span><h2>What can I help you with?</h2><p>Bring a question, a piece of context, or something you want to make.</p></div><Composer centered onSubmit={onStart} /><div className="suggestions" aria-label="Example prompts">{suggestions.map(({ icon: Icon, text }) => <button key={text} onClick={() => onStart(text)}><Icon size={17} /><span>{text}</span><ArrowRight size={15} /></button>)}</div></div></main>
}
