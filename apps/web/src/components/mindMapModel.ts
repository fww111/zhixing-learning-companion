export type MindMapTreeNode = {
  id: string;
  label: string;
  children: MindMapTreeNode[];
};

export type MindMapGraphRef = {
  name?: string;
  summary?: string;
};

export type MindMapGraphConstraints = {
  current_node?: MindMapGraphRef;
  parent?: MindMapGraphRef | null;
  predecessors?: MindMapGraphRef[];
  successors?: MindMapGraphRef[];
  related?: MindMapGraphRef[];
};

export type MindMapKnowledgeContext = {
  heading?: string;
  source_locator?: string;
  content?: string;
};

export type MindMapBuildContext = {
  topic?: string;
  graphConstraints?: MindMapGraphConstraints;
  knowledgeContext?: MindMapKnowledgeContext[];
  tags?: string[];
  recommendationReason?: string;
};

type ParsedLine = {
  label: string;
  detail: string;
  indent: number;
  headingDepth?: number;
  isMarked: boolean;
  isCompactStar: boolean;
};

const branchTitlePattern = /^(定义|定位|历史|版本|特点|特征|应用|示例|误区|关系|路径|结构|目标|重点|难点|语法|实践|总结|前置|后续)/;
const relationBranchPattern = /(关系|衔接|路径|图谱|结构)/;

export function buildMindMapTree(
  content: string,
  fallbackRoot: string,
  context: MindMapBuildContext = {}
): MindMapTreeNode {
  const root = parseStructuredContent(content, context.topic || fallbackRoot);
  if (!root.label) {
    root.label = context.topic || fallbackRoot;
  }

  const fallbackBranches = buildFallbackBranches(root.label, context, content);
  for (const branch of fallbackBranches) {
    if (root.children.length >= 6 && root.children.some((item) => item.children.length)) {
      break;
    }
    if (!root.children.some((item) => sameMeaning(item.label, branch.label))) {
      root.children.push(branch);
    }
  }

  if (root.children.length > 9) {
    root.children = compactBranches(root.children);
  }

  return {
    ...root,
    children: root.children
      .map((branch) => limitBranchDepth(branch))
      .filter((branch) => branch.label.length > 0)
  };
}

export function splitMindMapBranches(children: MindMapTreeNode[]): [MindMapTreeNode[], MindMapTreeNode[]] {
  const midpoint = Math.ceil(children.length / 2);
  return [children.slice(0, midpoint), children.slice(midpoint)];
}

function parseStructuredContent(content: string, fallbackRoot: string): MindMapTreeNode {
  const root = createNode("root", fallbackRoot);
  let currentBranch: MindMapTreeNode | undefined;
  let currentSubBranch: MindMapTreeNode | undefined;

  content
    .split("\n")
    .map(parseLine)
    .filter((line): line is ParsedLine => Boolean(line?.label))
    .forEach((line, index) => {
      if (line.headingDepth === 1 && index <= 1) {
        root.label = line.label;
        return;
      }

      if (shouldStartRootBranch(line, currentBranch)) {
        currentBranch = createNode(`branch-${root.children.length}-${slug(line.label)}`, line.label);
        root.children.push(currentBranch);
        currentSubBranch = undefined;
        appendDetail(currentBranch, line.detail);
        return;
      }

      if (!currentBranch) {
        currentBranch = createNode(`branch-${root.children.length}-${slug(line.label)}`, line.label);
        root.children.push(currentBranch);
        appendDetail(currentBranch, line.detail);
        return;
      }

      if (shouldStartSubBranch(line, currentBranch)) {
        currentSubBranch = createNode(`${currentBranch.id}-sub-${currentBranch.children.length}-${slug(line.label)}`, line.label);
        currentBranch.children.push(currentSubBranch);
        appendDetail(currentSubBranch, line.detail);
        return;
      }

      const target = currentSubBranch && line.indent > 0 ? currentSubBranch : currentBranch;
      const child = createNode(`${target.id}-leaf-${target.children.length}-${slug(line.label)}`, line.label);
      target.children.push(child);
      appendDetail(child, line.detail);
    });

  return root;
}

function parseLine(rawLine: string): ParsedLine | undefined {
  const trimmedRight = rawLine.trimEnd();
  const line = trimmedRight.trim();
  if (!line) {
    return undefined;
  }

  const indent = trimmedRight.length - trimmedRight.trimStart().length;
  const headingMatch = /^(#{1,6})\s*(.+)$/.exec(line);
  if (headingMatch) {
    return toParsedLine(cleanLabel(headingMatch[2]), "", indent, {
      headingDepth: headingMatch[1].length,
      isMarked: true,
      isCompactStar: false
    });
  }

  const compactStarMatch = /^(\*{1,3})([^\s*].*)$/.exec(line);
  if (compactStarMatch) {
    return toParsedLine(cleanLabel(compactStarMatch[2]), "", indent, {
      isMarked: true,
      isCompactStar: true
    });
  }

  const markerMatch = /^(?:[-*•]|(?:\d+(?:\.\d+)*[.)、]))\s+(.+)$/.exec(line);
  if (markerMatch) {
    const [label, detail] = splitLabelDetail(cleanLabel(markerMatch[1]));
    return toParsedLine(label, detail, indent, {
      isMarked: true,
      isCompactStar: false
    });
  }

  const [label, detail] = splitLabelDetail(cleanLabel(line));
  return toParsedLine(label, detail, indent, {
    isMarked: false,
    isCompactStar: false
  });
}

function toParsedLine(
  label: string,
  detail: string,
  indent: number,
  flags: { headingDepth?: number; isMarked: boolean; isCompactStar: boolean }
): ParsedLine | undefined {
  const cleaned = cleanLabel(label);
  if (!cleaned) {
    return undefined;
  }
  return {
    label: cleaned,
    detail: cleanLabel(detail),
    indent,
    ...flags
  };
}

function shouldStartRootBranch(line: ParsedLine, currentBranch: MindMapTreeNode | undefined): boolean {
  if (line.headingDepth && line.headingDepth <= 2) {
    return true;
  }
  if (!currentBranch) {
    return true;
  }
  if (line.indent > 0 || shouldStartSubBranch(line, currentBranch)) {
    return false;
  }
  if (line.isCompactStar) {
    return true;
  }
  return line.isMarked && line.label.length <= 18 && branchTitlePattern.test(line.label);
}

function shouldStartSubBranch(line: ParsedLine, currentBranch: MindMapTreeNode): boolean {
  if (line.headingDepth && line.headingDepth >= 3) {
    return true;
  }
  return Boolean(
    currentBranch.children.length &&
    (line.indent > 0 || relationBranchPattern.test(currentBranch.label)) &&
    line.isMarked &&
    line.label.length <= 20
  );
}

function appendDetail(node: MindMapTreeNode, detail: string) {
  if (!detail) {
    return;
  }
  node.children.push(createNode(`${node.id}-detail-${node.children.length}`, detail));
}

function buildFallbackBranches(
  rootLabel: string,
  context: MindMapBuildContext,
  content: string
): MindMapTreeNode[] {
  const constraints = context.graphConstraints;
  const evidenceHighlights = extractEvidenceHighlights(context.knowledgeContext, content);
  const currentSummary = constraints?.current_node?.summary || context.recommendationReason || "";

  return [
    createBranch("课程定位", [
      constraints?.parent?.name ? `所属章节：${constraints.parent.name}` : "",
      constraints?.current_node?.name ? `当前知识点：${constraints.current_node.name}` : rootLabel,
      currentSummary
    ]),
    createBranch("前置依赖", (constraints?.predecessors || []).map((item) => item.name || "").filter(Boolean)),
    createBranch("核心内容", evidenceHighlights),
    createBranch("后续衔接", (constraints?.successors || []).map((item) => item.name || "").filter(Boolean)),
    createBranch("相关拓展", [
      ...(constraints?.related || []).map((item) => item.name || "").filter(Boolean),
      ...(context.tags || [])
    ])
  ].filter((branch) => branch.children.length);
}

function extractEvidenceHighlights(knowledgeContext: MindMapKnowledgeContext[] | undefined, content: string): string[] {
  const contextHighlights = (knowledgeContext || [])
    .flatMap((item) => [
      item.heading,
      item.content?.split(/[。；;\n]/).find((part) => cleanLabel(part).length >= 8)
    ])
    .filter((item): item is string => Boolean(item))
    .map(cleanLabel)
    .filter(Boolean)
    .slice(0, 5);

  if (contextHighlights.length) {
    return contextHighlights;
  }

  return content
    .split(/[。；;\n]/)
    .map(cleanLabel)
    .filter((item) => item.length >= 8 && item.length <= 48)
    .slice(0, 5);
}

function compactBranches(children: MindMapTreeNode[]): MindMapTreeNode[] {
  const titledBranches = children.filter((child) => child.children.length);
  if (titledBranches.length >= 3 && titledBranches.length <= 9) {
    return titledBranches;
  }

  const compacted: MindMapTreeNode[] = [];
  let current: MindMapTreeNode | undefined;
  for (const child of children) {
    const looksLikeBranch = child.label.length <= 20 && branchTitlePattern.test(child.label);
    if (!current || looksLikeBranch) {
      current = createNode(`compact-${compacted.length}-${slug(child.label)}`, child.label);
      compacted.push(current);
      current.children.push(...child.children);
    } else {
      current.children.push(child);
    }
  }
  return compacted.slice(0, 9);
}

function limitBranchDepth(node: MindMapTreeNode): MindMapTreeNode {
  return {
    ...node,
    children: node.children.slice(0, 7).map((child) => ({
      ...child,
      children: child.children.slice(0, 4)
    }))
  };
}

function createBranch(label: string, children: string[]): MindMapTreeNode {
  const branch = createNode(`fallback-${slug(label)}`, label);
  branch.children = children
    .map(cleanLabel)
    .filter(Boolean)
    .filter((item, index, array) => array.findIndex((candidate) => sameMeaning(candidate, item)) === index)
    .slice(0, 6)
    .map((item, index) => createNode(`${branch.id}-${index}-${slug(item)}`, item));
  return branch;
}

function createNode(id: string, label: string): MindMapTreeNode {
  return {
    id,
    label: cleanLabel(label),
    children: []
  };
}

function splitLabelDetail(label: string): [string, string] {
  const match = /^(.{2,18}?)[：:]\s*(.{4,})$/.exec(label);
  if (!match) {
    return [label, ""];
  }
  return [match[1], match[2]];
}

function cleanLabel(label: string | undefined): string {
  return (label || "")
    .replace(/^#+\s*/, "")
    .replace(/^[-*•]\s*/, "")
    .replace(/^(?:\d+[)、]|\d+\.)\s+/, "")
    .replace(/\*\*/g, "")
    .replace(/[`>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function sameMeaning(left: string, right: string): boolean {
  return cleanLabel(left).toLowerCase() === cleanLabel(right).toLowerCase();
}

function slug(label: string): string {
  return cleanLabel(label).slice(0, 16).replace(/[^\p{L}\p{N}]+/gu, "-") || "node";
}
