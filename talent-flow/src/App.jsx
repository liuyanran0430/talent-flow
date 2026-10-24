import { AppProvider, useApp } from './context/AppContext'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import Jobs from './pages/Jobs'
import Requirements from './pages/Requirements'
import ImportResume from './pages/ImportResume'
import Candidates from './pages/Candidates'
import Report from './pages/Report'

function Pages() {
  const { section } = useApp()
  switch (section) {
    case 'jobs':
      return <Jobs />
    case 'requirements':
      return <Requirements />
    case 'import':
      return <ImportResume />
    case 'candidates':
      return <Candidates />
    case 'report':
      return <Report />
    default:
      return <Jobs />
  }
}

function Shell() {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <main className="flex-1 min-w-0">
        <Header />
        <Pages />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
