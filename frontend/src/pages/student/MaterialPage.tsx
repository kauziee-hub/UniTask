import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ErrorNote, Spinner } from '../../components/ui'
import { api, apiUrl, openFile } from '../../lib/api'
import type { MaterialDetail } from '../../lib/types'
import { useLoad } from '../../lib/useLoad'
import { MATERIAL_KINDS as KINDS } from '../../lib/study'

export function MaterialPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') ?? 1)
  const { data: material, error } = useLoad<MaterialDetail>(`/api/materials/${id}`)
  const { data: text } = useLoad<{ text: string; page: number }>(material && material.page_count ? `/api/materials/${id}/pages/${page}` : null)
  const [preview, setPreview] = useState<string | null>(null)
  const [view, setView] = useState<'original' | 'text'>('original')
  const isPdf = material?.content_type === 'application/pdf'
  const isImage = material?.content_type.startsWith('image/')

  useEffect(() => {
    if (!material || !(isPdf || isImage)) return
    let cancelled = false
    api.get<{ url: string }>(`/api/materials/${material.id}/file?inline=true`).then((link) => {
      if (!cancelled) setPreview(apiUrl(link.url))
    }).catch(() => setView('text'))
    return () => {
      cancelled = true
    }
  }, [material, isPdf, isImage])

  if (!material) return <main className="page">{error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}</main>
  const pages = Array.from({ length: material.page_count ?? 0 }, (_, i) => i + 1)
  const showOriginal = view === 'original' && (isPdf || isImage) && preview

  return (
    <main className="page wide">
      <nav className="crumbs"><Link to="/library">Library</Link>{material.course && <><span>/</span><Link to={`/subjects/${material.course.id}`}>{material.course.name}</Link></>}</nav>
      <header className="page-head">
        <div>
          <p className="kicker">{KINDS.find((k) => k.key === material.kind)?.label}{material.year ? ` · ${material.year}` : ''} · {material.page_count ?? 0} pages</p>
          <h1 className="title page-title">{material.title}</h1>
        </div>
        <div className="row page-actions">
          {(isPdf || isImage) && (
            <div className="segmented" role="group" aria-label="View">
              <button type="button" aria-pressed={view === 'original'} onClick={() => setView('original')}>Original</button>
              <button type="button" aria-pressed={view === 'text'} onClick={() => setView('text')}>Extracted text</button>
            </div>
          )}
          <button className="btn" type="button" onClick={() => openFile(`/api/materials/${material.id}/file`)}>Download <ExternalLink size={13} /></button>
          <Link className="btn primary" to={`/tutor?material=${material.id}${material.course ? `&course=${material.course.id}` : ''}`}>Ask about this</Link>
        </div>
      </header>
      {material.status !== 'ready' && <div className="note" style={{ marginBottom: 14 }}>{material.error ?? `Status: ${material.status}.`}</div>}
      {material.topics.length > 0 && (
        <p className="small" style={{ marginBottom: 14 }}>
          <span className="muted">Covers: </span>
          {material.topics.map((t, i) => (
            <span key={t.topic_id}>
              {i > 0 && ', '}
              <Link to={`/topics/${t.topic_id}`}>{t.title}</Link>
              <button className="btn ghost small" type="button" style={{ height: 20, padding: '0 4px' }} onClick={() => setParams({ page: String(t.pages[0]) })}>p.{t.pages.join(', ')}</button>
            </span>
          ))}
        </p>
      )}
      <div className="viewer">
        <div className="pages" aria-label="Pages">
          {pages.map((n) => (
            <button key={n} type="button" aria-current={n === page} onClick={() => setParams({ page: String(n) })}>
              Page {n}{material.empty_pages.includes(n) ? ' · no text' : ''}
            </button>
          ))}
        </div>
        {showOriginal ? (
          isPdf ? <iframe key={page} title={material.title} src={`${preview}#page=${page}`} /> : <img className="preview" src={preview} alt={material.title} />
        ) : (
          <div className="page-text" aria-label={`Page ${page} text`}>{text?.text || 'No text on this page.'}</div>
        )}
      </div>
    </main>
  )
}
