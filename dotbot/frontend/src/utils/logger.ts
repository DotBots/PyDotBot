import pino from "pino";

interface LogObject {
  time: string;
  level: number;
  module?: string;
  msg: string;
  [key: string]: unknown;
}

const levelToLabel = (level: number): { label: string; style: string } => {
  if (level > 40) return { label: "[ERROR]  ", style: "color:red;font-weight:bold" };
  if (level > 30) return { label: "[WARNING]", style: "color:yellow;font-weight:bold" };
  if (level > 20) return { label: "[INFO]   ", style: "color:white;font-weight:bold" };
  return { label: "[DEBUG]  ", style: "color:green;font-weight:bold" };
};

const logger = pino({
  browser: {
    asObject: true,
    write: (o: unknown) => {
      const log = o as LogObject;
      console.log(
        `${log.time} - %c ${levelToLabel(log.level).label}%c${log.module ? " - " + log.module : ""} - ${log.msg}`,
        levelToLabel(log.level).style,
        "color:white"
      );
    },
  },
  level: process.env.REACT_APP_LOG_LEVEL || "info",
  timestamp: pino.stdTimeFunctions.isoTime,
  serializers: {},
});

export default logger;
