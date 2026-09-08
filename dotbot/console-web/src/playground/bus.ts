import mqtt, { type MqttClient } from "mqtt";

// The page's only transport. Two methods, so a qrkey envelope is a second
// implementation rather than a rewrite, and so the fake world can run the same
// discovery code with no broker at all.

export interface AppBus {
  /** Returns the unsubscribe. The topic may carry MQTT wildcards. */
  subscribe(topic: string, cb: (payload: unknown, topic: string) => void): () => void;
  publish(topic: string, payload: unknown, opts?: { retain?: boolean }): void;
}

/** MQTT topic-filter match, wildcards included, as the broker does it. */
export function topicMatches(filter: string, topic: string): boolean {
  const f = filter.split("/");
  const t = topic.split("/");
  for (let i = 0; i < f.length; i++) {
    if (f[i] === "#") return true;
    if (i >= t.length) return false;
    if (f[i] !== "+" && f[i] !== t[i]) return false;
  }
  return f.length === t.length;
}

function decode(raw: Uint8Array): unknown {
  // An empty payload is the retained-message delete, and the callers read it
  // as "this app is gone", so it must survive as null rather than throw.
  if (raw.length === 0) return null;
  try {
    return JSON.parse(new TextDecoder().decode(raw));
  } catch {
    return null;
  }
}

/**
 * A bus with no broker: the fake world's apps talk to the page in process.
 * Retained payloads are replayed to a late subscriber, as a broker would.
 */
export class MemoryBus implements AppBus {
  private readonly subs = new Map<string, Set<(payload: unknown, topic: string) => void>>();
  private readonly retained = new Map<string, unknown>();

  subscribe(topic: string, cb: (payload: unknown, topic: string) => void): () => void {
    const set = this.subs.get(topic) ?? new Set();
    set.add(cb);
    this.subs.set(topic, set);
    for (const [held, payload] of this.retained) {
      if (topicMatches(topic, held)) cb(payload, held);
    }
    return () => set.delete(cb);
  }

  publish(topic: string, payload: unknown, opts?: { retain?: boolean }): void {
    if (opts?.retain) {
      if (payload === null) this.retained.delete(topic);
      else this.retained.set(topic, payload);
    }
    for (const [filter, set] of this.subs) {
      if (!topicMatches(filter, topic)) continue;
      for (const cb of set) cb(payload, topic);
    }
  }
}

/** Plain MQTT over WebSockets, the same connect qrkey's hook makes. */
export class PlainMqttBus implements AppBus {
  private readonly client: MqttClient;
  private readonly subs = new Map<string, Set<(payload: unknown, topic: string) => void>>();

  constructor(url: string, clientId: string) {
    this.client = mqtt.connect(url, { clientId, reconnectPeriod: 2000 });
    this.client.on("message", (topic, raw) => {
      const payload = decode(raw);
      for (const [filter, set] of this.subs) {
        if (!topicMatches(filter, topic)) continue;
        for (const cb of set) cb(payload, topic);
      }
    });
  }

  get connected(): boolean {
    return this.client.connected;
  }

  onStateChange(cb: (connected: boolean) => void): void {
    this.client.on("connect", () => cb(true));
    this.client.on("close", () => cb(false));
    this.client.on("error", () => cb(false));
  }

  subscribe(topic: string, cb: (payload: unknown, topic: string) => void): () => void {
    const set = this.subs.get(topic) ?? new Set();
    if (set.size === 0) this.client.subscribe(topic);
    set.add(cb);
    this.subs.set(topic, set);
    return () => {
      set.delete(cb);
      if (set.size === 0) {
        this.subs.delete(topic);
        this.client.unsubscribe(topic);
      }
    };
  }

  publish(topic: string, payload: unknown, opts?: { retain?: boolean }): void {
    const body = payload === null ? "" : JSON.stringify(payload);
    this.client.publish(topic, body, { retain: opts?.retain ?? false });
  }

  close(): void {
    this.client.end(true);
  }
}
