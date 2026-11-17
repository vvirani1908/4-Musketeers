import { useEffect, useState } from 'react'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

function App() {
  const [connectionStatus, setConnectionStatus] = useState('Checking backend connection...')
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    fetch(`${apiBaseUrl}/health`)
      .then((response) => {
        if (!response.ok) throw new Error('Backend returned an error response')
        return response.json()
      })
      .then((data) => {
        setIsConnected(data.status === 'ok')
        setConnectionStatus(data.status === 'ok' ? 'Backend connected' : 'Backend unavailable')
      })
      .catch(() => {
        setIsConnected(false)
        setConnectionStatus('Backend unavailable')
      })
  }, [])

  return (
    <main className="page-shell">
      <section className="hero-card" aria-labelledby="page-title">
        <p className="eyebrow">CMPE 272 · 4-Musketeers</p>
        <h1 id="page-title">AI-Powered Enterprise Knowledge Portal</h1>
        <p className="intro">
          A foundation for discovering, understanding, and asking questions about enterprise knowledge.
        </p>
        <div className={`status ${isConnected ? 'status-connected' : 'status-disconnected'}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {connectionStatus}
        </div>
      </section>
    </main>
  )
}

export default App
