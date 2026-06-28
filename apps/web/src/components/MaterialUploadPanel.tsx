import { useEffect, useRef, useState } from "react";
import { FileUp, Loader2, RefreshCw, Trash2 } from "lucide-react";
import {
  deleteMaterial,
  listMaterials,
  rebuildVectorIndex,
  uploadMaterial,
  type Course,
  type CourseMaterial
} from "../api/client";
import { summarizeUploadSelection, uploadProgressLabel } from "./materialUploadModel";
import { materialStatusesSettledAfterBackgroundWork } from "./materialStatusModel";

interface MaterialUploadPanelProps {
  token: string;
  course: Course;
  onMaterialsChanged: () => void;
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function materialStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    parsed: "已入库",
    index_failed: "待重建索引",
    failed: "解析失败",
    queued: "已排队",
    pending: "处理中",
    processing: "解析中",
    mineru_submitted: "已提交 MinerU",
    mineru_polling: "MinerU 精准解析中",
    ocr_running: "OCR 中",
    chunking: "切片中",
    indexing: "索引中"
  };
  return labels[status] ?? status;
}

function isActiveMaterialStatus(status: string): boolean {
  return [
    "queued",
    "pending",
    "processing",
    "mineru_submitted",
    "mineru_polling",
    "ocr_running",
    "chunking",
    "indexing"
  ].includes(status);
}

export function MaterialUploadPanel({ token, course, onMaterialsChanged }: MaterialUploadPanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [materials, setMaterials] = useState<CourseMaterial[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadIndex, setUploadIndex] = useState(0);
  const [deletingId, setDeletingId] = useState<number | undefined>();
  const [reindexing, setReindexing] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState("");
  const courseIdRef = useRef(course.id);
  const materialsRef = useRef<CourseMaterial[]>([]);
  const materialsRequestRef = useRef(0);

  async function loadMaterials() {
    const requestCourseId = course.id;
    const requestId = materialsRequestRef.current + 1;
    materialsRequestRef.current = requestId;
    setListLoading(true);
    setError("");
    try {
      const nextMaterials = await listMaterials(token, requestCourseId);
      if (courseIdRef.current !== requestCourseId || materialsRequestRef.current !== requestId) {
        return;
      }
      if (materialStatusesSettledAfterBackgroundWork(materialsRef.current, nextMaterials)) {
        onMaterialsChanged();
      }
      materialsRef.current = nextMaterials;
      setMaterials(nextMaterials);
    } catch (caught) {
      if (courseIdRef.current !== requestCourseId || materialsRequestRef.current !== requestId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "加载课程资料失败");
    } finally {
      if (courseIdRef.current === requestCourseId && materialsRequestRef.current === requestId) {
        setListLoading(false);
      }
    }
  }

  useEffect(() => {
    courseIdRef.current = course.id;
    setFiles([]);
    setMaterials([]);
    materialsRef.current = [];
    setListLoading(false);
    setLoading(false);
    setDeletingId(undefined);
    setReindexing(false);
    setStatusMessage("");
    setError("");
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    void loadMaterials();
  }, [course.id, token]);

  useEffect(() => {
    if (!materials.some((material) => isActiveMaterialStatus(material.parse_status))) {
      return;
    }
    const timerId = window.setInterval(() => {
      void loadMaterials();
    }, 3000);
    return () => window.clearInterval(timerId);
  }, [materials, course.id, token]);

  async function handleUpload() {
    if (files.length === 0) {
      setError("请选择 PDF、PPT 或 PPTX 文件");
      return;
    }

    setLoading(true);
    setUploadIndex(0);
    setStatusMessage("");
    setError("");
    const uploadCourseId = course.id;
    const uploadedMaterials: CourseMaterial[] = [];
    try {
      for (const [index, selectedFile] of files.entries()) {
        setUploadIndex(index);
        const material = await uploadMaterial(token, uploadCourseId, selectedFile);
        uploadedMaterials.push(material);
        if (courseIdRef.current !== uploadCourseId) {
          return;
        }
      }
      setMaterials((current) => [
        ...uploadedMaterials.reverse(),
        ...current.filter((item) => !uploadedMaterials.some((material) => material.id === item.id))
      ]);
      materialsRef.current = [
        ...uploadedMaterials,
        ...materialsRef.current.filter((item) => !uploadedMaterials.some((material) => material.id === item.id))
      ];
      setFiles([]);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      onMaterialsChanged();
      const activeCount = uploadedMaterials.filter((material) => material.parse_status === "queued").length;
      const indexFailedCount = uploadedMaterials.filter((material) => material.parse_status === "index_failed").length;
      setStatusMessage(
        uploadedMaterials.length > 1
          ? `${uploadedMaterials.length} 份资料已上传，后台会逐份交给 MinerU 精准解析、切片并构建向量索引。`
          : activeCount > 0
            ? "资料已上传，后台正在进行 MinerU 精准解析、切片和构建向量索引。"
            : indexFailedCount > 0
              ? "资料已解析并写入 MySQL，向量索引失败，可点击重建向量索引重试。"
              : "资料已解析并写入本地知识库。"
      );
      void loadMaterials();
    } catch (caught) {
      if (courseIdRef.current !== uploadCourseId) {
        return;
      }
      if (uploadedMaterials.length > 0) {
        setMaterials((current) => [
          ...uploadedMaterials.reverse(),
          ...current.filter((item) => !uploadedMaterials.some((material) => material.id === item.id))
        ]);
        materialsRef.current = [
          ...uploadedMaterials,
          ...materialsRef.current.filter((item) => !uploadedMaterials.some((material) => material.id === item.id))
        ];
        onMaterialsChanged();
        void loadMaterials();
      }
      setError(caught instanceof Error ? caught.message : "上传资料失败");
      setStatusMessage(uploadedMaterials.length > 0 ? `${uploadedMaterials.length} 份资料已上传，后续文件上传失败，请检查后重试。` : "");
    } finally {
      if (courseIdRef.current === uploadCourseId) {
        setLoading(false);
        setUploadIndex(0);
      }
    }
  }

  const selectedSummary = summarizeUploadSelection(files);

  async function handleDelete(material: CourseMaterial) {
    if (!window.confirm(`确定删除资料「${material.filename}」吗？`)) {
      return;
    }

    const deleteCourseId = course.id;
    setDeletingId(material.id);
    setStatusMessage("");
    setError("");
    try {
      await deleteMaterial(token, deleteCourseId, material.id);
      if (courseIdRef.current !== deleteCourseId) {
        return;
      }
      setMaterials((current) => current.filter((item) => item.id !== material.id));
      materialsRef.current = materialsRef.current.filter((item) => item.id !== material.id);
      onMaterialsChanged();
      setStatusMessage("资料和对应知识切片已清除。");
      void loadMaterials();
    } catch (caught) {
      if (courseIdRef.current !== deleteCourseId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "删除资料失败");
    } finally {
      if (courseIdRef.current === deleteCourseId) {
        setDeletingId(undefined);
      }
    }
  }

  async function handleRebuildVectorIndex() {
    const rebuildCourseId = course.id;
    setReindexing(true);
    setStatusMessage("");
    setError("");
    try {
      const result = await rebuildVectorIndex(token, rebuildCourseId);
      if (courseIdRef.current !== rebuildCourseId) {
        return;
      }
      setStatusMessage(`后台已开始重建 ${result.indexed_chunks} 个知识切片索引，完成前课程资料会显示“索引中”。`);
      void loadMaterials();
    } catch (caught) {
      if (courseIdRef.current !== rebuildCourseId) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "重建向量索引失败");
    } finally {
      if (courseIdRef.current === rebuildCourseId) {
        setReindexing(false);
      }
    }
  }

  return (
    <section className="kb-section material-panel">
      <div className="kb-section-head">
        <div>
          <h3>课程资料</h3>
          <p>{materials.length > 0 ? `已上传 ${materials.length} 份资料` : "上传 PDF/PPT 后自动解析为知识切片。"}</p>
        </div>
        <button className="icon-action" aria-label="刷新课程资料" disabled={listLoading} onClick={loadMaterials}>
          <RefreshCw className={listLoading ? "spin" : ""} size={16} />
        </button>
      </div>

      <div className="upload-zone-card material-upload-zone">
        <strong>上传 PDF / PPT / PPTX</strong>
        <span>可一次选择多个 PDF/PPT/PPTX，上传后系统会逐份提交 MinerU 解析，不阻塞当前页面操作。</span>
        <div className="upload-row">
        <label className="file-picker">
          <span>资料文件</span>
          <input
            ref={inputRef}
            accept=".pdf,.ppt,.pptx"
            multiple
            type="file"
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>
        <button className="secondary-action upload-button" disabled={loading || files.length === 0} onClick={handleUpload}>
          {loading ? <Loader2 className="spin" size={16} /> : <FileUp size={16} />}
          {loading ? uploadProgressLabel(uploadIndex, files.length) : files.length > 1 ? "批量上传" : "上传"}
        </button>
        </div>
      </div>

      {selectedSummary ? <p className="kb-hint">{selectedSummary.label}（共 {formatBytes(selectedSummary.totalBytes)}）</p> : null}
      <button
        className="secondary-action compact-button"
        disabled={reindexing || materials.length === 0}
        onClick={handleRebuildVectorIndex}
      >
        {reindexing ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
        {reindexing ? "重建中" : "重建向量索引"}
      </button>
      {statusMessage ? <p className="kb-hint">{statusMessage}</p> : null}
      {error ? <div className="error compact-error">{error}</div> : null}
      <div className="material-list">
        {materials.length > 0 ? (
          materials.map((material) => (
            <div className="upload-result" key={material.id}>
              <div className="upload-result-body">
                <strong>{material.filename}</strong>
                <span>{materialStatusLabel(material.parse_status)}</span>
                <span>{formatBytes(material.size_bytes)}</span>
                {material.ocr_used ? <span>OCR</span> : null}
                {material.parse_error ? <small>{material.parse_error}</small> : null}
              </div>
              <button
                aria-label={`删除资料 ${material.filename}`}
                className="icon-action delete-material-button"
                disabled={deletingId === material.id}
                onClick={() => handleDelete(material)}
                title="删除资料"
              >
                {deletingId === material.id ? <Loader2 className="spin" size={16} /> : <Trash2 size={16} />}
              </button>
            </div>
          ))
        ) : (
          <div className="empty compact-empty">{listLoading ? "正在加载资料" : "暂无课程资料"}</div>
        )}
      </div>
    </section>
  );
}
