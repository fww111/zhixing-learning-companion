import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { GraphConstraints, KnowledgeContextItem, Resource } from "../api/client";
import {
  buildMindMapTree,
  splitMindMapBranches,
  type MindMapTreeNode
} from "./mindMapModel";

interface MindMapViewerProps {
  graphConstraints?: GraphConstraints;
  knowledgeContext?: KnowledgeContextItem[];
  resource?: Resource;
  topic?: string;
}

type MindMapSide = "left" | "right";

type BranchPlacement = {
  branch: MindMapTreeNode;
  side: MindMapSide;
  tone: number;
};

type ConnectorPath = {
  color: string;
  d: string;
  id: string;
  width: number;
};

type ConnectorState = {
  height: number;
  paths: ConnectorPath[];
  width: number;
};

const branchColors = ["#ef4444", "#a855f7", "#22c55e", "#3b82f6", "#f59e0b", "#14b8a6"];

export function MindMapViewer({
  graphConstraints,
  knowledgeContext,
  resource,
  topic
}: MindMapViewerProps) {
  const viewRef = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const branchRefs = useRef<Record<string, HTMLElement | null>>({});
  const leafRefs = useRef<Record<string, HTMLElement | null>>({});
  const [connectors, setConnectors] = useState<ConnectorState>({ height: 0, paths: [], width: 0 });
  const root = useMemo(
    () => buildMindMapTree(resource?.content ?? "", topic || resource?.title || "知识点思维导图", {
      graphConstraints,
      knowledgeContext,
      recommendationReason: resource?.recommendation_reason,
      tags: resource?.tags,
      topic: topic || resource?.topic
    }),
    [graphConstraints, knowledgeContext, resource, topic]
  );

  if (!resource && !root.children.length) {
    return null;
  }

  const [leftBranches, rightBranches] = splitMindMapBranches(root.children);
  const branchPlacements = useMemo<BranchPlacement[]>(
    () => [
      ...leftBranches.map((branch, index) => ({ branch, side: "left" as const, tone: index })),
      ...rightBranches.map((branch, index) => ({ branch, side: "right" as const, tone: index + leftBranches.length }))
    ],
    [leftBranches, rightBranches]
  );

  useLayoutEffect(() => {
    const view = viewRef.current;
    const rootElement = rootRef.current;
    if (!view || !rootElement) {
      return undefined;
    }

    const measure = () => {
      const viewRect = view.getBoundingClientRect();
      const rootRect = rootElement.getBoundingClientRect();
      const nextPaths: ConnectorPath[] = [];

      for (const placement of branchPlacements) {
        const branchElement = branchRefs.current[placement.branch.id];
        if (!branchElement) {
          continue;
        }
        const branchRect = branchElement.getBoundingClientRect();
        const color = branchColors[placement.tone % branchColors.length];
        const fromX = placement.side === "left"
          ? rootRect.left - viewRect.left
          : rootRect.right - viewRect.left;
        const fromY = rootRect.top + rootRect.height / 2 - viewRect.top;
        const toX = placement.side === "left"
          ? branchRect.right - viewRect.left
          : branchRect.left - viewRect.left;
        const toY = branchRect.top + branchRect.height / 2 - viewRect.top;
        const pull = Math.max(82, Math.abs(toX - fromX) * 0.48);
        const branchCurve = placement.side === "left"
          ? `M ${fromX} ${fromY} C ${fromX - pull} ${fromY}, ${toX + pull} ${toY}, ${toX} ${toY}`
          : `M ${fromX} ${fromY} C ${fromX + pull} ${fromY}, ${toX - pull} ${toY}, ${toX} ${toY}`;

        nextPaths.push({
          color,
          d: branchCurve,
          id: `${placement.branch.id}-root`,
          width: 4
        });

        for (const leaf of placement.branch.children) {
          const leafElement = leafRefs.current[leaf.id];
          if (!leafElement) {
            continue;
          }
          const leafRect = leafElement.getBoundingClientRect();
          const leafStartX = placement.side === "left"
            ? branchRect.left - viewRect.left + branchRect.width * 0.34
            : branchRect.right - viewRect.left - branchRect.width * 0.34;
          const leafStartY = branchRect.bottom - viewRect.top;
          const leafEndX = placement.side === "left"
            ? leafRect.right - viewRect.left
            : leafRect.left - viewRect.left;
          const leafEndY = leafRect.top + leafRect.height / 2 - viewRect.top;
          const leafPull = Math.max(28, Math.abs(leafEndY - leafStartY) * 0.52);
          const leafCurve = `M ${leafStartX} ${leafStartY} C ${leafStartX} ${leafStartY + leafPull}, ${leafEndX} ${leafEndY - leafPull}, ${leafEndX} ${leafEndY}`;
          nextPaths.push({
            color,
            d: leafCurve,
            id: `${placement.branch.id}-${leaf.id}`,
            width: 2
          });
        }
      }

      setConnectors({
        height: Math.max(1, viewRect.height),
        paths: nextPaths,
        width: Math.max(1, viewRect.width)
      });
    };

    const frame = window.requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    observer.observe(view);
    observer.observe(rootElement);
    Object.values(branchRefs.current).forEach((element) => element && observer.observe(element));
    Object.values(leafRefs.current).forEach((element) => element && observer.observe(element));
    window.addEventListener("resize", measure);

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [branchPlacements]);

  return (
    <section className="panel mindmap-panel">
      <h2 className="compact-heading">思维导图预览</h2>
      <div className="mindmap-view" aria-label={`${root.label} 思维导图`} ref={viewRef}>
        <svg
          aria-hidden="true"
          className="mindmap-connectors"
          height={connectors.height}
          viewBox={`0 0 ${connectors.width} ${connectors.height}`}
          width={connectors.width}
        >
          {connectors.paths.map((path) => (
            <path
              d={path.d}
              fill="none"
              key={path.id}
              stroke={path.color}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={path.width}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
        <div className="mindmap-side left">
          {leftBranches.map((branch, index) => (
            <MindMapBranch
              branch={branch}
              key={branch.id}
              setBranchRef={(element) => { branchRefs.current[branch.id] = element; }}
              setLeafRef={(leafId, element) => { leafRefs.current[leafId] = element; }}
              side="left"
              tone={index}
            />
          ))}
        </div>
        <div className="mindmap-root" ref={rootRef}>
          <span>{root.label}</span>
        </div>
        <div className="mindmap-side right">
          {rightBranches.map((branch, index) => (
            <MindMapBranch
              branch={branch}
              key={branch.id}
              setBranchRef={(element) => { branchRefs.current[branch.id] = element; }}
              setLeafRef={(leafId, element) => { leafRefs.current[leafId] = element; }}
              side="right"
              tone={index + leftBranches.length}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function MindMapBranch({
  branch,
  setBranchRef,
  setLeafRef,
  side,
  tone
}: {
  branch: MindMapTreeNode;
  setBranchRef: (element: HTMLElement | null) => void;
  setLeafRef: (leafId: string, element: HTMLElement | null) => void;
  side: MindMapSide;
  tone: number;
}) {
  const children = branch.children.slice(0, 6);
  return (
    <article className={`mindmap-branch ${side} tone-${tone % 6}`}>
      <div className="mindmap-branch-line" />
      <strong ref={setBranchRef}>{branch.label}</strong>
      {children.length ? (
        <div className="mindmap-leaves">
          {children.map((leaf) => (
            <div className="mindmap-leaf-row" key={leaf.id}>
              <span ref={(element) => setLeafRef(leaf.id, element)}>{leaf.label}</span>
              {leaf.children.length ? (
                <div className="mindmap-subleaves">
                  {leaf.children.slice(0, 3).map((subLeaf) => <em key={subLeaf.id}>{subLeaf.label}</em>)}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}
