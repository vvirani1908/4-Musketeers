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
  const [selectedFiles, setSelectedFiles] = useState([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])
  const [documentFilter, setDocumentFilter] = useState('')
  const [documentSort, setDocumentSort] = useState('newest')
  const [documentsError, setDocumentsError] = useState('')
  const [documentMessage, setDocumentMessage] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [isBulkDeleting, setIsBulkDeleting] = useState(false)
  const [openingSourceId, setOpeningSourceId] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [question, setQuestion] = useState('')
  const [aiAnswer, setAiAnswer] = useState(null)
  const [isAsking, setIsAsking] = useState(false)
  const [aiError, setAiError] = useState('')

  function resetUserScopedState() {
    setCurrentUser(null)
    setEmail('')
    setPassword('')
    setDocuments([])
    setSelectedFiles([])
    setSelectedDocumentIds([])
    setDocumentFilter('')
    setDocumentSort('newest')
    setDocumentsError('')
    setDocumentMessage('')
    setIsUploading(false)
    setSearchQuery('')
    setSearchResults([])
    setIsSearching(false)
    setQuestion('')
    setAiAnswer(null)
    setIsAsking(false)
    setAiError('')
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
        if (response.status === 401) throw new Error('SESSION_EXPIRED')
        if (!response.ok) throw new Error('Could not verify your session')
        return response.json()
      })
      .then(setCurrentUser)
      .catch((error) => {
        if (error.message !== 'SESSION_EXPIRED') {
          setAuthError('Could not verify your session. Please check the backend connection.')
          return
        }
        sessionStorage.removeItem('access_token')
        setToken(null)
        resetUserScopedState()
        setAuthError('Your session has expired. Please log in again.')
      })
  }, [token])

  useEffect(() => {
    setSelectedDocumentIds((selectedIds) => selectedIds.filter((id) => documents.some((document) => document.id === id)))
  }, [documents])

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
        const response = await authenticatedFetch(`${apiBaseUrl}/documents`, {
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
    const response = await authenticatedFetch(`${apiBaseUrl}/documents`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Could not load documents')
    setDocuments(data)
  }

  function handleSessionExpired() {
    sessionStorage.removeItem('access_token')
    resetUserScopedState()
    setToken(null)
    setAuthError('Your session has expired. Please log in again.')
  }

  async function authenticatedFetch(url, options = {}) {
    const response = await fetch(url, options)
    if (response.status === 401) {
      handleSessionExpired()
      throw new Error('Your session has expired. Please log in again.')
    }
    return response
  }

  function handleFileSelection(event) {
    const files = Array.from(event.target.files || [])
    setSelectedFiles(files.map((file, index) => ({
      file,
      id: `${file.name}-${file.size}-${file.lastModified}-${index}`,
      status: 'queued',
      error: '',
    })))
    setDocumentsError('')
    setDocumentMessage('')
  }

  async function handleUpload(event) {
    event.preventDefault()
    if (!selectedFiles.length || isUploading) return
    const uploadForm = event.currentTarget

    setIsUploading(true)
    setDocumentsError('')
    setDocumentMessage('')
    let successfulUploads = 0
    const failedUploads = []

    for (const selected of selectedFiles) {
      setSelectedFiles((files) => files.map((item) => (
        item.id === selected.id ? { ...item, status: 'uploading', error: '' } : item
      )))

      try {
        const form = new FormData()
        form.append('file', selected.file)
        const response = await authenticatedFetch(`${apiBaseUrl}/documents`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Upload failed')
        successfulUploads += 1
        setSelectedFiles((files) => files.map((item) => (
          item.id === selected.id ? { ...item, status: 'success' } : item
        )))
      } catch (error) {
        failedUploads.push(`${selected.file.name}: ${error.message}`)
        setSelectedFiles((files) => files.map((item) => (
          item.id === selected.id ? { ...item, status: 'failed', error: error.message } : item
        )))
      }
    }

    uploadForm.reset()
    try {
      await reloadDocuments()
    } catch (error) {
      setDocumentsError(error.message)
    }
    setDocumentMessage(`${successfulUploads} of ${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'} uploaded successfully.`)
    if (failedUploads.length) setDocumentsError(`Some uploads failed: ${failedUploads.join(' · ')}`)
    setIsUploading(false)
  }

  async function handleDownload(document) {
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/documents/${document.id}/download`, {
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
      const response = await authenticatedFetch(`${apiBaseUrl}/documents/${document.id}`, {
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

  function toggleDocumentSelection(documentId) {
    setSelectedDocumentIds((selectedIds) => selectedIds.includes(documentId)
      ? selectedIds.filter((id) => id !== documentId)
      : [...selectedIds, documentId])
  }

  async function handleBulkDelete() {
    if (!selectedDocumentIds.length || isBulkDeleting) return
    const selectedDocuments = documents.filter((document) => selectedDocumentIds.includes(document.id))
    if (!window.confirm(`Delete ${selectedDocuments.length} selected document${selectedDocuments.length === 1 ? '' : 's'}? This cannot be undone.`)) return

    setIsBulkDeleting(true)
    setDocumentsError('')
    const failed = []
    let deleted = 0

    for (const document of selectedDocuments) {
      try {
        const response = await authenticatedFetch(`${apiBaseUrl}/documents/${document.id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) {
          const data = await response.json()
          throw new Error(data.detail || 'Delete failed')
        }
        deleted += 1
      } catch (error) {
        failed.push(`${document.filename}: ${error.message}`)
      }
    }

    setSelectedDocumentIds([])
    try {
      await reloadDocuments()
    } catch (error) {
      setDocumentsError(error.message)
    }
    setDocumentMessage(`${deleted} of ${selectedDocuments.length} document${selectedDocuments.length === 1 ? '' : 's'} deleted.`)
    if (failed.length) setDocumentsError(`Some deletions failed: ${failed.join(' · ')}`)
    setIsBulkDeleting(false)
  }

  async function handleOpenSource(source) {
    const sourceKey = `${source.document_id}-${source.page_number || 'document'}`
    setOpeningSourceId(sourceKey)
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/documents/${source.document_id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Could not open source document')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = window.document.createElement('a')
      link.href = source.page_number ? `${url}#page=${source.page_number}` : url
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (error) {
      setDocumentsError(error.message)
    } finally {
      setOpeningSourceId('')
    }
  }

  async function handleReindex(document) {
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/documents/${document.id}/index`, {
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
    if (!searchQuery.trim() || isSearching) return
    setIsSearching(true)
    setDocumentsError('')
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/documents/search?q=${encodeURIComponent(searchQuery)}`, {
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

  async function handleAsk(event) {
    event.preventDefault()
    if (!question.trim() || isAsking) return
    setIsAsking(true)
    setAiError('')
    setAiAnswer(null)
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/rag/ask`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: question.trim() }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not get an AI answer')
      setAiAnswer(data)
    } catch (error) {
      setAiError(error.message)
    } finally {
      setIsAsking(false)
    }
  }

  function submitOnEnter(event) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.isComposing) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  function uploadStatusLabel(selected) {
    if (selected.status === 'uploading') return 'Uploading…'
    if (selected.status === 'success') return 'Uploaded; indexing started'
    if (selected.status === 'failed') return `Upload failed${selected.error ? `: ${selected.error}` : ''}`
    return 'Ready to upload'
  }

  function processingLabel(document) {
    if (document.processing_status === 'failed') return `Indexing failed: ${document.processing_error || 'Unknown processing error'}`
    if (document.processing_status === 'indexed') return 'Indexed and searchable'
    if (document.processing_status === 'indexing') return 'Indexing…'
    return 'Waiting to index…'
  }

  const visibleDocuments = documents
    .filter((document) => document.filename.toLowerCase().includes(documentFilter.trim().toLowerCase()))
    .sort((first, second) => documentSort === 'filename'
      ? first.filename.localeCompare(second.filename)
      : new Date(second.created_at) - new Date(first.created_at))
  const allVisibleDocumentsSelected = visibleDocuments.length > 0
    && visibleDocuments.every((document) => selectedDocumentIds.includes(document.id))

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
                <div>
                  <p className="section-kicker">Admin action</p>
                  <label htmlFor="document-file">Upload PDF files</label>
                </div>
                <div className="upload-controls">
                  <label
                    className="file-picker-button"
                    htmlFor="document-file"
                    role="button"
                    tabIndex="0"
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        window.document.getElementById('document-file')?.click()
                      }
                    }}
                  >
                    Choose PDF files
                  </label>
                  <input
                    id="document-file"
                    type="file"
                    multiple
                    accept="application/pdf,.pdf"
                    onChange={handleFileSelection}
                  />
                  <span className="selected-file-count">
                    {selectedFiles.length ? `${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'} selected` : 'No files selected'}
                  </span>
                  <button type="submit" disabled={!selectedFiles.length || isUploading}>
                    {isUploading ? 'Uploading…' : 'Upload files'}
                  </button>
                </div>
                <small>PDF files only, up to 10 MB each. Files are processed independently.</small>
                {selectedFiles.length > 0 && (
                  <ul className="upload-status-list" aria-live="polite">
                    {selectedFiles.map((selected) => (
                      <li key={selected.id} className={`upload-status upload-status-${selected.status}`}>
                        <span>{selected.file.name}</span>
                        <small>{uploadStatusLabel(selected)}</small>
                      </li>
                    ))}
                  </ul>
                )}
              </form>
            )}

            <form className="search-form" onSubmit={handleSearch}>
              <div>
                <p className="section-kicker">Find knowledge</p>
                <label htmlFor="search-query">Semantic Search</label>
              </div>
              <div className="search-controls">
                <input
                  id="search-query"
                  type="search"
                  placeholder="Try a phrase or topic"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onKeyDown={submitOnEnter}
                />
                <button type="submit" disabled={!searchQuery.trim() || isSearching}>
                  {isSearching ? 'Searching...' : 'Search'}
                </button>
              </div>
            </form>

            <form className="ask-form" onSubmit={handleAsk}>
              <div>
                <p className="section-kicker">Synthesize answers</p>
                <label htmlFor="ai-question">Ask AI</label>
              </div>
              <div className="ask-controls">
                <textarea
                  id="ai-question"
                  rows="3"
                  placeholder="Ask a question about the indexed knowledge base"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={submitOnEnter}
                />
                <button type="submit" disabled={!question.trim() || isAsking}>
                  {isAsking ? 'Thinking...' : 'Ask AI'}
                </button>
              </div>
              {aiError && <p className="auth-error" role="alert">{aiError}</p>}
              {aiAnswer && (
                <div className="ai-answer" aria-live="polite">
                  <h3>Answer</h3>
                  {aiAnswer.provider && aiAnswer.model && (
                    <small className="answer-provider">
                      Generated by {aiAnswer.provider.charAt(0).toUpperCase() + aiAnswer.provider.slice(1)} · {aiAnswer.model}
                    </small>
                  )}
                  <p>{aiAnswer.answer}</p>
                  {aiAnswer.sources.length > 0 && (
                    <div>
                      <h4>Source transparency</h4>
                      <p className="source-note">
                        Sources marked “Cited” were explicitly referenced by the generated answer. The others were retrieved as context but were not explicitly cited.
                      </p>
                      <ul className="source-list">
                        {aiAnswer.sources.map((source, index) => (
                          <li key={`${source.document_id}-${source.page_number}-${index}`}>
                            <span className={source.cited ? 'source-cited' : 'source-retrieved'}>
                              {source.cited ? 'Cited' : 'Retrieved'}
                            </span>{' '}
                            <button
                              type="button"
                              className="source-link"
                              onClick={() => handleOpenSource(source)}
                              disabled={openingSourceId === `${source.document_id}-${source.page_number || 'document'}`}
                            >
                              <strong>{source.source_id || `source-${index + 1}`}</strong> · {source.filename}{source.page_number ? ` · Page ${source.page_number}` : ''} · Document {source.document_id}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
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
            <div className="document-tools">
              <label htmlFor="document-filter">Filter by filename</label>
              <input
                id="document-filter"
                type="search"
                placeholder="Filter documents"
                value={documentFilter}
                onChange={(event) => setDocumentFilter(event.target.value)}
              />
              <label htmlFor="document-sort">Sort</label>
              <select id="document-sort" value={documentSort} onChange={(event) => setDocumentSort(event.target.value)}>
                <option value="newest">Newest first</option>
                <option value="filename">Filename A–Z</option>
              </select>
            </div>
            {currentUser.role === 'admin' && documents.length > 0 && (
              <div className="bulk-controls">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setSelectedDocumentIds(allVisibleDocumentsSelected ? [] : visibleDocuments.map((document) => document.id))}
                  disabled={!visibleDocuments.length || isBulkDeleting}
                >
                  {allVisibleDocumentsSelected ? 'Clear selection' : 'Select all'}
                </button>
                <button
                  type="button"
                  className="danger-button"
                  onClick={handleBulkDelete}
                  disabled={!selectedDocumentIds.length || isBulkDeleting}
                >
                  {isBulkDeleting ? 'Deleting…' : `Delete selected (${selectedDocumentIds.length})`}
                </button>
                <small>{selectedDocumentIds.length ? `${selectedDocumentIds.length} selected` : 'Select documents to delete'}</small>
              </div>
            )}
            {documents.length === 0 ? (
              <p className="empty-state">No documents have been uploaded yet.</p>
            ) : visibleDocuments.length === 0 ? (
              <p className="empty-state">No documents match this filename filter.</p>
            ) : (
              <ul className="document-list">
                {visibleDocuments.map((document) => (
                  <li key={document.id} className="document-row">
                    <div>
                      {currentUser.role === 'admin' && (
                        <input
                          className="document-checkbox"
                          type="checkbox"
                          aria-label={`Select ${document.filename}`}
                          checked={selectedDocumentIds.includes(document.id)}
                          onChange={() => toggleDocumentSelection(document.id)}
                          disabled={isBulkDeleting}
                        />
                      )}
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
