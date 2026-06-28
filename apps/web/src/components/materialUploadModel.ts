export interface UploadSelectionSummary {
  fileCount: number;
  totalBytes: number;
  names: string[];
  label: string;
}

export function summarizeUploadSelection(files: File[]): UploadSelectionSummary | undefined {
  if (files.length === 0) {
    return undefined;
  }
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const names = files.map((file) => file.name);
  return {
    fileCount: files.length,
    totalBytes,
    names,
    label: files.length === 1 ? `待上传：${files[0].name}` : `待上传 ${files.length} 个文件：${names.join("、")}`
  };
}

export function uploadProgressLabel(currentIndex: number, total: number): string {
  if (total <= 1) {
    return "上传中";
  }
  return `上传中 ${currentIndex + 1}/${total}`;
}
