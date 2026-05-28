import React, { useEffect, useRef, useState } from "react";

interface AnimatedNumberProps {
  value: number;
  formatter?: (value: number) => string;
  className?: string;
  positiveClassName?: string;
  negativeClassName?: string;
  neutralClassName?: string;
  durationMs?: number;
}

export const AnimatedNumber: React.FC<AnimatedNumberProps> = ({
  value,
  formatter,
  className = "",
  positiveClassName = "text-emerald-300",
  negativeClassName = "text-rose-300",
  neutralClassName = "text-white",
  durationMs = 1000,
}) => {
  const previousRef = useRef<number>(value);
  const [isPulsing, setIsPulsing] = useState<boolean>(false);
  const [direction, setDirection] = useState<"up" | "down" | "flat">("flat");

  useEffect(() => {
    if (value === previousRef.current) {
      return;
    }

    setDirection(value > previousRef.current ? "up" : "down");
    setIsPulsing(true);

    const timeoutId = window.setTimeout(() => {
      setIsPulsing(false);
      setDirection("flat");
    }, durationMs);

    previousRef.current = value;
    return () => window.clearTimeout(timeoutId);
  }, [durationMs, value]);

  const toneClass =
    direction === "up" ? positiveClassName : direction === "down" ? negativeClassName : neutralClassName;

  return (
    <span
      className={`inline-block transform-gpu transition-all duration-500 ease-out ${toneClass} ${
        isPulsing ? "scale-105" : "scale-100"
      } ${className}`}
    >
      {formatter ? formatter(value) : value.toString()}
    </span>
  );
};
