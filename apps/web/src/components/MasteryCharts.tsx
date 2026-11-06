import { useMemo } from "react";
import { RadarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import EChartsReactCore from "echarts-for-react/lib/core";
import type { AssessmentDimensionCard, AssessmentTrendPoint } from "../pages/courseAssessmentDashboardModel";

echarts.use([RadarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const CHART_TEXT_COLOR = "#64748b";
const CHART_LINE_COLOR = "#e2e8f0";

export interface MasterySlice {
  key: string;
  label: string;
  value: number;
  color: string;
}

/** 七维评估雷达：课堂/题库/编程/行为 + 达标率/薄弱控制/覆盖。 */
export function MasteryRadarChart({ cards }: { cards: AssessmentDimensionCard[] }) {
  const option = useMemo<EChartsCoreOption>(() => {
    const indicators = cards.map((card) => ({ name: card.label, max: 100 }));
    const values = cards.map((card) => Math.max(0, Math.min(100, card.score)));
    return {
      tooltip: {},
      radar: {
        indicator: indicators,
        radius: "68%",
        center: ["50%", "52%"],
        axisName: { color: CHART_TEXT_COLOR, fontSize: 11, fontWeight: 700 },
        splitLine: { lineStyle: { color: CHART_LINE_COLOR } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: CHART_LINE_COLOR } }
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: values,
              name: "多维评估",
              areaStyle: { color: "rgba(99,102,241,0.18)" },
              lineStyle: { color: "#6366f1", width: 2 },
              itemStyle: { color: "#6366f1" },
              symbolSize: 4
            }
          ]
        }
      ]
    };
  }, [cards]);

  return (
    <EChartsReactCore
      echarts={echarts}
      option={option}
      opts={{ renderer: "canvas" }}
      style={{ height: 260, width: "100%" }}
    />
  );
}

/** 掌握度五态分布环图。 */
export function MasteryDistributionChart({ slices }: { slices: MasterySlice[] }) {
  const option = useMemo<EChartsCoreOption>(() => {
    return {
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: {
        bottom: 0,
        icon: "circle",
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: CHART_TEXT_COLOR, fontSize: 11, fontWeight: 700 }
      },
      series: [
        {
          type: "pie",
          radius: ["52%", "78%"],
          center: ["50%", "44%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: "#ffffff", borderWidth: 2, borderRadius: 4 },
          label: { show: false },
          data: slices
            .filter((slice) => slice.value > 0)
            .map((slice) => ({
              name: slice.label,
              value: slice.value,
              itemStyle: { color: slice.color }
            }))
        }
      ]
    };
  }, [slices]);

  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  if (!total) {
    return <div className="chart-empty">完成评估后，这里会展示知识点掌握度五态分布。</div>;
  }
  return <EChartsReactCore echarts={echarts} option={option} opts={{ renderer: "canvas" }} style={{ height: 240, width: "100%" }} />;
}

/** 历次评估分数趋势折线。 */
export function ScoreTrendChart({ points }: { points: AssessmentTrendPoint[] }) {
  const option = useMemo<EChartsCoreOption>(() => {
    return {
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const first = list[0] as { name?: string; value?: number; data?: { topic?: string } } | undefined;
          const topic = first?.data && typeof first.data === "object" ? first.data.topic : "";
          return `${first?.name || ""}<br/>综合得分 ${first?.value ?? 0}%${topic ? `<br/>${topic}` : ""}`;
        }
      },
      grid: { left: 40, right: 16, top: 16, bottom: 28 },
      xAxis: {
        type: "category",
        data: points.map((point) => point.label),
        axisLine: { lineStyle: { color: CHART_LINE_COLOR } },
        axisLabel: { color: CHART_TEXT_COLOR, fontSize: 10 }
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        splitLine: { lineStyle: { color: CHART_LINE_COLOR } },
        axisLabel: { color: CHART_TEXT_COLOR, fontSize: 10, formatter: "{value}" }
      },
      series: [
        {
          type: "line",
          data: points.map((point) => ({ value: point.score, topic: point.topic })),
          smooth: true,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { color: "#6366f1", width: 2.5 },
          itemStyle: { color: "#6366f1", borderColor: "#ffffff", borderWidth: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(99,102,241,0.28)" },
                { offset: 1, color: "rgba(99,102,241,0.02)" }
              ]
            }
          }
        }
      ]
    };
  }, [points]);

  if (!points.length) {
    return <div className="chart-empty">完成第一次课堂评估后，这里会展示你的分数趋势。</div>;
  }
  return <EChartsReactCore echarts={echarts} option={option} opts={{ renderer: "canvas" }} style={{ height: 220, width: "100%" }} />;
}
