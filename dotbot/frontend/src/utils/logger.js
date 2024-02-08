import pino from "pino";

const levelToLabel = (level) => {
    if (level > 40) return {label: "[ERROR]  ", style: "color:red;font-weight:bold"};
    if (level > 30) return {label: "[WARNING]", style: "color:yellow;font-weight:bold"};
    if (level > 20) return {label: "[INFO]   ", style: "color:white;font-weight:bold"};
    return {label: "[DEBUG]  ", style: "color:green;font-weight:bold"};
};

const logger = pino({
  browser: {
    asObject: true,
    write: (o) => {
        console.log(`${o.time} - %c ${levelToLabel(o.level).label}%c${o.module ? " - " + o.module: ""} - ${o.msg}`, levelToLabel(o.level).style, "color:white");
    }
  },
  level: process.env.REACT_APP_LOG_LEVEL || 'info',
  timestamp: pino.stdTimeFunctions.isoTime,
  serialize: true,
});

export default logger;
