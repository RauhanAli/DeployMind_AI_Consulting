"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui";

// Recharts writes colours as SVG presentation attributes, where CSS var() does not resolve: use literal colours.
export const CHART = { primary: "#3b4cca", grid: "#d9dee8", text: "#6b7280" };
const PALETTE = [CHART.primary, "#16a37f", "#e0a21b", "#dc4b3e", "#8b5cf6", "#0ea5b7", "#64748b"];
const axis = { fontSize: 11, fill: CHART.text };
const tooltipStyle = { background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 };

export function OpportunityMatrix({ opportunities }: { opportunities: any[] }) {
  const data = opportunities.map((o) => ({ x: 6 - o.implementation_complexity, y: o.business_impact, z: o.priority_score, name: o.title, rank: o.rank }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prioritisation matrix</CardTitle>
        <CardDescription>Business impact vs. feasibility (inverse complexity). Bubble size = priority score.</CardDescription>
      </CardHeader>
      <CardContent className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 20, bottom: 25, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
            <XAxis type="number" dataKey="x" domain={[0, 6]} tick={axis} label={{ value: "Feasibility →", position: "insideBottom", offset: -12, fontSize: 11 }} />
            <YAxis type="number" dataKey="y" domain={[0, 6]} tick={axis} label={{ value: "Impact →", angle: -90, position: "insideLeft", fontSize: 11 }} />
            <ZAxis type="number" dataKey="z" range={[120, 700]} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v: any, n: any) => [v, n]} labelFormatter={() => ""}
              content={({ payload }) => payload?.[0] ? (
                <div style={tooltipStyle} className="p-2"><p className="font-medium">#{payload[0].payload.rank} {payload[0].payload.name}</p>
                  <p>Priority {payload[0].payload.z}</p></div>) : null} />
            <Scatter isAnimationActive={false} data={data}>{data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} fillOpacity={0.75} />)}</Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function TimeSeries({ title, description, data, series, kind = "line", height = 240, xKey = "t", format }: {
  title: string; description?: string; data: any[]; series: { key: string; label: string }[]; kind?: "line" | "area" | "bar";
  height?: number; xKey?: string; format?: (v: number) => string;
}) {
  const tick = (v: string) => {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? v : d.toLocaleString("en-GB", data.length > 48 ? { day: "2-digit", month: "short" } : { hour: "2-digit", minute: "2-digit", day: "2-digit" });
  };
  const Chart = kind === "area" ? AreaChart : kind === "bar" ? BarChart : LineChart;
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">{title}</CardTitle>{description && <CardDescription>{description}</CardDescription>}</CardHeader>
      <CardContent style={{ height }}>
        {data.length === 0 ? <p className="flex h-full items-center justify-center text-sm text-muted-foreground">No data in this window</p> : (
          <ResponsiveContainer width="100%" height="100%">
            <Chart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
              <XAxis dataKey={xKey} tickFormatter={tick} tick={axis} minTickGap={24} />
              <YAxis tick={axis} tickFormatter={format} width={52} />
              <Tooltip contentStyle={tooltipStyle} labelFormatter={(l) => tick(String(l))} formatter={(v: any) => (format ? format(Number(v)) : v)} />
              {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
              {series.map((s, i) =>
                kind === "area" ? <Area isAnimationActive={false} key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={PALETTE[i]} fill={PALETTE[i]} fillOpacity={0.15} /> :
                kind === "bar" ? <Bar isAnimationActive={false} key={s.key} dataKey={s.key} name={s.label} fill={PALETTE[i]} radius={[3, 3, 0, 0]} /> :
                <Line isAnimationActive={false} key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={PALETTE[i]} dot={false} strokeWidth={2} />)}
            </Chart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

export function HBar({ title, data, valueKey, labelKey, format }: { title: string; data: any[]; valueKey: string; labelKey: string; format?: (v: number) => string }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent style={{ height: Math.max(160, data.length * 36 + 40) }}>
        {data.length === 0 ? <p className="text-sm text-muted-foreground">No data</p> : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" tick={axis} tickFormatter={format} />
              <YAxis type="category" dataKey={labelKey} tick={axis} width={150} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: any) => (format ? format(Number(v)) : v)} />
              <Bar isAnimationActive={false} dataKey={valueKey} fill={CHART.primary} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
