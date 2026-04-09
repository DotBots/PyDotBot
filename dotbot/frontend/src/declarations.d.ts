declare module 'geodist' {
  interface GeoPoint {
    lat: number;
    lon: number;
  }
  interface GeoDistOptions {
    exact?: boolean;
    unit?: string;
  }
  function geodist(p1: GeoPoint, p2: GeoPoint, options?: GeoDistOptions): number;
  export = geodist;
}

declare module 'use-interval' {
  function useInterval(callback: () => void | Promise<void>, delay: number | null): void;
  export default useInterval;
}

declare module 'qrkey' {
  import { Dispatch, SetStateAction } from 'react';

  interface QrKeyMessage {
    topic: string;
    payload: {
      request?: number;
      data?: unknown;
      cmd?: number;
    };
  }

  interface QrKeyMqttData {
    pin: string | null;
    mqtt_host: string | null;
    mqtt_port: number | null;
    mqtt_version: number;
    mqtt_use_ssl: boolean;
    mqtt_username: string | null;
    mqtt_password: string | null;
  }

  interface QrKeyOptions {
    rootTopic: string | undefined;
    setQrKeyMessage: Dispatch<SetStateAction<QrKeyMessage | null>>;
    searchParams: URLSearchParams;
    setSearchParams: Dispatch<SetStateAction<URLSearchParams>>;
  }

  type PublishFn = (topic: string, message: unknown) => void;
  type PublishCommandFn = (address: string, application: number, command: string, data: unknown) => Promise<void>;
  type SendRequestFn = (request: { request: number; reply: string }) => void;

  export function useQrKey(options: QrKeyOptions): [
    boolean,
    string,
    QrKeyMqttData | null,
    Dispatch<SetStateAction<QrKeyMqttData | null>>,
    PublishFn,
    PublishCommandFn,
    SendRequestFn
  ];

  export type { QrKeyMessage, QrKeyMqttData };
}
