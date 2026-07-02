import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

interface ProgressRingProps {
  /** Progress fraction 0..1. Clamped. */
  progress: number;
  /** Diameter in px. */
  size?: number;
  /** Stroke width in px. */
  stroke?: number;
  /** Optional label shown in the center. */
  label?: string;
}

/**
 * A circular progress ring built directly on react-native-svg (no charting
 * library needed for this). Works on web and native.
 */
export function ProgressRing({
  progress,
  size = 56,
  stroke = 6,
  label,
}: ProgressRingProps) {
  const p = Math.max(0, Math.min(1, progress));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * p;
  const gap = circumference - dash;

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      <Svg width={size} height={size}>
        {/* Background track */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#1e293b"
          strokeWidth={stroke}
          fill="none"
        />
        {/* Progress arc — rotated so it starts at the top. */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={p >= 1 ? "#22c55e" : "#6366f1"}
          strokeWidth={stroke}
          strokeDasharray={`${dash} ${gap}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          rotation={-90}
          originX={size / 2}
          originY={size / 2}
          fill="none"
        />
      </Svg>
      {label ? (
        <View style={styles.labelWrap}>
          <Text style={styles.labelPct}>{Math.round(p * 100)}%</Text>
          <Text style={styles.labelSub}>{label}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center" },
  labelWrap: {
    position: "absolute",
    alignItems: "center",
    justifyContent: "center",
  },
  labelPct: { color: "#f1f5f9", fontSize: 12, fontWeight: "700" },
  labelSub: { color: "#94a3b8", fontSize: 8, marginTop: 1 },
});
