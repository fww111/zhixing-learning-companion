import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import {
  listChunks,
  semanticSearch,
  type Course,
  type KnowledgeChunk,
  type SemanticSearchResult
} from "../api/client";

interface KnowledgeChunksPanelProps {
  token: string;
  course: Course;
  refreshKey: number;
}

type ChunkDisplayItem = {
  id: string;
  sourceLocator: string;
  heading: string;
  content: string;
  meta: string;
};

function chunkToDisplay(chunk: KnowledgeChunk): ChunkDisplayItem {
  return {
    id: `chunk-${chunk.id}`,
    sourceLocator: chunk.source_locator || `#${chunk.chunk_index + 1}`,
    heading: chunk.heading || `切片 ${chunk.chunk_index + 1}`,
    content: chunk.content,
    meta: `${chunk.token_count} tokens`
  };
}

function searchToDisplay(result: SemanticSearchResult, chunks: KnowledgeChunk[]): ChunkDisplayItem {
  const matchedChunk = chunks.find((chunk) => chunk.id === result.chunk_id);
  const heading = matchedChunk?.heading || (result.chunk_id ? `切片 ${result.chunk_id}` : result.id);
  const distance = typeof result.distance === "number" ? `distance ${result.distance.toFixed(4)}` : "semantic match";

  return {
    id: `search-${result.id}`,
    sourceLocator: result.source_locator || matchedChunk?.source_locator || "-",
    heading,
    content: result.content || matchedChunk?.content || "",
    meta: distance
  };
}

export function KnowledgeChunksPanel({ token, course, refreshKey }: KnowledgeChunksPanelProps) {
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [searchResults, setSearchResults] = useState<SemanticSearchResult[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const courseIdRef = useRef(course.id);
  const chunksRequestRef = useRef(0);
  const searchRequestRef = useRef(0);

  async function loadChunks() {
    const requestCourseId = course.id;
    const requestId = chunksRequestRef.current + 1;
    chunksRequestRef.current = requestId;
    setLoading(true);
    setError("");
    try {
      const nextChunks = await listChunks(token, requestCourseId);
      if (courseIdRef.current !== requestCourseId || chunksRequestRef.current !== requestId) {
        return;
      }
      setChunks(nextChunks);
    } catch (caught) {
      if (courseIdRef.current !== requestCourseId || chunksRequestRef.current !== requestId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "加载知识切片失败");
    } finally {
      if (courseIdRef.current === requestCourseId && chunksRequestRef.current === requestId) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    courseIdRef.current = course.id;
    setChunks([]);
    setSearchResults([]);
    setQuery("");
    setLoading(false);
    setSearching(false);
    setError("");
    void loadChunks();
  }, [course.id, refreshKey]);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setSearchResults([]);
      return;
    }

    setSearching(true);
    setError("");
    const requestCourseId = course.id;
    const requestId = searchRequestRef.current + 1;
    searchRequestRef.current = requestId;
    try {
      const results = await semanticSearch(token, requestCourseId, trimmed);
      if (courseIdRef.current !== requestCourseId || searchRequestRef.current !== requestId) {
        return;
      }
      setSearchResults(results);
    } catch (caught) {
      if (courseIdRef.current !== requestCourseId || searchRequestRef.current !== requestId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "语义检索失败");
    } finally {
      if (courseIdRef.current === requestCourseId && searchRequestRef.current === requestId) {
        setSearching(false);
      }
    }
  }

  const visibleItems = useMemo(() => {
    if (searchResults.length > 0) {
      return searchResults.map((result) => searchToDisplay(result, chunks));
    }
    return chunks.map(chunkToDisplay);
  }, [chunks, searchResults]);

  return (
    <section className="kb-section chunks-panel">
      <div className="kb-section-head">
        <div>
          <h3>知识切片</h3>
          <p>{searchResults.length > 0 ? `检索结果 ${searchResults.length} 条` : `已解析 ${chunks.length} 条`}</p>
        </div>
        <button className="icon-action" aria-label="刷新知识切片" disabled={loading} onClick={loadChunks}>
          <RefreshCw className={loading ? "spin" : ""} size={16} />
        </button>
      </div>

      <form className="search-row" onSubmit={handleSearch}>
        <input
          aria-label="语义检索"
          placeholder="按概念、公式或问题检索"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="secondary-action" disabled={searching} type="submit">
          <Search size={16} />
          {searching ? "检索中" : "检索"}
        </button>
      </form>

      {error ? <div className="error compact-error">{error}</div> : null}

      <div className="chunk-list">
        {visibleItems.length > 0 ? (
          visibleItems.map((item) => (
            <article className="chunk-item" key={item.id}>
              <div className="chunk-meta">
                <span>{item.sourceLocator}</span>
                <small>{item.meta}</small>
              </div>
              <strong>{item.heading}</strong>
              <p>{item.content}</p>
            </article>
          ))
        ) : (
          <div className="empty compact-empty">{loading ? "正在加载知识切片" : "暂无知识切片"}</div>
        )}
      </div>
    </section>
  );
}
