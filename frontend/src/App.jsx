import { useEffect, useState } from 'react'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

function App() {
  const [connectionStatus, setConnectionStatus] = useState('Checking backend connection...')
  const [isConnected, setIsConnected] = useState(false)
  const [token, setToken] = useState(() => sessionStorage.getItem('access_token'))
  const [currentUser, setCurrentUser] = useState(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [isLoggingIn, setIsLoggingIn] = useState(false)
  const [documents, setDocuments] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [documentsError, setDocumentsError] = useState('')
  const [documentMessage, setDocumentMessage] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)

  function resetUserScopedState() {
    setCurrentUser(null)
    setEmail('')
    setPassword('')
    setDocuments([])
    setSelectedFile(null)
    setDocumentsError('')
    setDocumentMessage('')
    setIsUploading(false)
    setSearchQuery('')
    setSearchResults([])
    setIsSearching(false)
  }

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

  useEffect(() => {
    if (!token) {
      resetUserScopedState()
      return
    }

    fetch(`${apiBaseUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error('Session expired')
        return response.json()
      })
      .then(setCurrentUser)
      .catch(() => {
        sessionStorage.removeItem('access_token')
        setToken(null)
        setAuthError('Your session has expired. Please log in again.')
      })
  }, [token])

  useEffect(() => {
    if (!token || !documents.some((document) => ['pending', 'indexing'].includes(document.processing_status))) return undefined
    const interval = window.setInterval(() => {
      reloadDocuments().catch((error) => setDocumentsError(error.message))
    }, 2000)
    return () => window.clearInterval(interval)
  }, [token, documents])

  useEffect(() => {
    if (!token) {
      setDocuments([])
      return
    }

    async function loadDocuments() {
      try {
        const response = await fetch(`${apiBaseUrl}/documents`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Could not load documents')
        setDocuments(data)
        setDocumentsError('')
      } catch (error) {
        setDocumentsError(error.message)
      }
    }

    loadDocuments()
  }, [token])

  async function handleLogin(event) {
    event.preventDefault()
    setAuthError('')
    setIsLoggingIn(true)

    try {
      const form = new URLSearchParams({ username: email, password })
      const response = await fetch(`${apiBaseUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Login failed')

      sessionStorage.setItem('access_token', data.access_token)
      resetUserScopedState()
      setToken(data.access_token)
      setPassword('')
    } catch (error) {
      setAuthError(error.message)
    } finally {
      setIsLoggingIn(false)
    }
  }

  function handleLogout() {
    sessionStorage.removeItem('access_token')
    resetUserScopedState()
    setToken(null)
    setAuthError('')
  }

  async function reloadDocuments() {
    const response = await fetch(`${apiBaseUrl}/documents`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Could not load documents')
    setDocuments(data)
  }

  async function handleUpload(event) {
    event.preventDefault()
    if (!selectedFile) return

    setIsUploading(true)
    setDocumentsError('')
    setDocumentMessage('')
    try {
      const form = new FormData()
      form.append('file', selectedFile)
      const response = await fetch(`${apiBaseUrl}/documents`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Upload failed')
      setSelectedFile(null)
      event.target.reset()
      setDocumentMessage(`${data.filename} uploaded successfully.`)
      await reloadDocuments()
    } catch (error) {
      setDocumentsError(error.message)
    } finally {
      setIsUploading(false)
    }
  }

  async function handleDownload(document) {
    try {
      const response = await fetch(`${apiBaseUrl}/documents/${document.id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Download failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = window.document.createElement('a')
      link.href = url
      link.download = document.filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setDocumentsError(error.message)
    }
  }

  async function handleDelete(document) {
    if (!window.confirm(`Delete ${document.filename}?`)) return

    try {
      const response = await fetch(`${apiBaseUrl}/documents/${document.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Delete failed')
      }
      setDocumentMessage(`${document.filename} deleted.`)
      await reloadDocuments()
    } catch (error) {
      setDocumentsError(error.message)
    }
  }

  async function handleReindex(document) {
    try {
      const response = await fetch(`${apiBaseUrl}/documents/${document.id}/index`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Re-indexing failed')
      setDocumentMessage(`${document.filename} re-indexing requested.`)
      await reloadDocuments()
    } catch (error) {
      setDocumentsError(error.message)
    }
  }

  async function handleSearch(event) {
    event.preventDefault()
    if (!searchQuery.trim()) return
    setIsSearching(true)
    setDocumentsError('')
    try {
      const response = await fetch(`${apiBaseUrl}/documents/search?q=${encodeURIComponent(searchQuery)}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Search failed')
      setSearchResults(data)
    } catch (error) {
      setDocumentsError(error.message)
    } finally {
      setIsSearching(false)
    }
  }

  function processingLabel(document) {
    if (document.processing_status === 'failed') return `Indexing failed: ${document.processing_error || 'Unknown processing error'}`
    if (document.processing_status === 'indexed') return 'Indexed and searchable'
    if (document.processing_status === 'indexing') return 'Indexing…'
    return 'Waiting to index…'
  }

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

        {currentUser ? (
          <div className="account-panel">
            <p className="account-label">Signed in as</p>
            <p className="account-email">{currentUser.email}</p>
            <p className="account-role">Role: {currentUser.role}</p>
            <button type="button" className="secondary-button" onClick={handleLogout}>
              Log out
            </button>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleLogin}>
            <h2>Sign in</h2>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {authError && <p className="auth-error" role="alert">{authError}</p>}
            <button type="submit" disabled={isLoggingIn}>
              {isLoggingIn ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        )}

        {currentUser && (
          <section className="documents-panel" aria-labelledby="documents-title">
            <div className="documents-heading">
              <div>
                <p className="eyebrow">Knowledge library</p>
                <h2 id="documents-title">Documents</h2>
              </div>
              <span className="document-count">{documents.length}</span>
            </div>

            {currentUser.role === 'admin' && (
              <form className="upload-form" onSubmit={handleUpload}>
                <label htmlFor="document-file">Upload a PDF</label>
                <div className="upload-controls">
                  <input
                    id="document-file"
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={(event) => setSelectedFile(event.target.files[0] || null)}
                    required
                  />
                  <button type="submit" disabled={!selectedFile || isUploading}>
                    {isUploading ? 'Uploading...' : 'Upload'}
                  </button>
                </div>
                <small>PDF files only, up to 10 MB.</small>
              </form>
            )}

            <form className="search-form" onSubmit={handleSearch}>
              <label htmlFor="search-query">Search indexed documents</label>
              <div className="search-controls">
                <input
                  id="search-query"
                  type="search"
                  placeholder="Try a phrase or topic"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
                <button type="submit" disabled={!searchQuery.trim() || isSearching}>
                  {isSearching ? 'Searching...' : 'Search'}
                </button>
              </div>
            </form>

            {searchQuery && searchResults.length === 0 && !isSearching && (
              <p className="empty-state">No matching indexed content.</p>
            )}
            {searchResults.length > 0 && (
              <div className="search-results" aria-live="polite">
                <h3>Search results</h3>
                {searchResults.map((result) => (
                  <article key={`${result.document_id}-${result.page_number}-${result.snippet}`} className="search-result">
                    <strong>{result.title}</strong>
                    <small>{result.page_number ? `Page ${result.page_number} · ` : ''}{Math.round(result.similarity * 100)}% match</small>
                    <details>
                      <summary>View context</summary>
                      <p>{result.snippet}</p>
                    </details>
                  </article>
                ))}
              </div>
            )}

            {documentMessage && <p className="success-message" role="status">{documentMessage}</p>}
            {documentsError && <p className="auth-error" role="alert">{documentsError}</p>}
            {documents.length === 0 ? (
              <p className="empty-state">No documents have been uploaded yet.</p>
            ) : (
              <ul className="document-list">
                {documents.map((document) => (
                  <li key={document.id} className="document-row">
                    <div>
                      <strong>{document.filename}</strong>
                      <small>Uploaded by user {document.uploaded_by}</small>
                      <small className={`processing-status processing-${document.processing_status}`}>
                        {processingLabel(document)}
                      </small>
                    </div>
                    <div className="document-actions">
                      <button type="button" className="secondary-button" onClick={() => handleDownload(document)}>
                        Download
                      </button>
                      {currentUser.role === 'admin' && (
                        <>
                          {document.processing_status === 'failed' && (
                            <button type="button" className="secondary-button" onClick={() => handleReindex(document)}>
                              Retry indexing
                            </button>
                          )}
                          <button type="button" className="danger-button" onClick={() => handleDelete(document)}>
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </section>
    </main>
  )
}

export default App
