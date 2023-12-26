/* eslint jsx-a11y/aria-role: 0 */

import { useCallback, useState } from "react";
import axios from 'axios';
import useWebSocket from 'react-use-websocket';
import './PinCode.css';

const websocketUrl = `${process.env.REACT_APP_DOTBOTS_WS_URL}/controller/ws/status`;

export const NotificationType = {
  None: 0,
  Reload: 1,
  Update: 2,
  PinCodeUpdate: 3,
};

const apiFetchPinCode = async () => {
  return await axios.get(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/mqtt/pin_code`,
  ).then(res => res.data);
}

const apiFetchQrCode = async () => {
  return await axios.get(
    `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/mqtt/pin_code/qr_code`,
  ).then(res => res.data);
}

const Animate = ({ children, on, transition }) => {
  return (on === undefined)
    ? <>{children}</>
    : <span className={transition} key={on}>{children}</span>
}

export const PinCode = () => {
  const [ pinCode, setPinCode ] = useState();
  const [ qrCode, setQrCode ] = useState();

  const fetchPinCode = useCallback(async () => {
    const data = await apiFetchPinCode().catch(error => console.log(error));
    if (data) {
      setPinCode(data.pin);
    }
  }, [setPinCode]
  );

  const fetchQrCode = useCallback(async () => {
    const data = await apiFetchQrCode().catch(error => console.log(error));
    if (data) {
      let parser = new DOMParser();
      let qr_code = parser.parseFromString(data, "image/svg+xml").documentElement.outerHTML;
      setQrCode(qr_code);
    }
  }, [setQrCode]
  );

  const onWsOpen = () => {
    console.log('websocket opened');
    fetchPinCode();
    fetchQrCode();
  };

  const onWsMessage = (event) => {
    console.log('websocket message');
    const message = JSON.parse(event.data);
    if (message.cmd === NotificationType.PinCodeUpdate) {
      setPinCode(message.pin_code);
      fetchQrCode();
    }
  };

  useWebSocket(websocketUrl, {
    onOpen: () => onWsOpen(),
    onClose: () => console.log("websocket closed"),
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: (event) => true,
  });

  return (
    <div className="PinCode" role="PinCode">
      {qrCode &&
      <Animate on={qrCode} transition="FadeIn">
        <div role="QrCode" className="Pop" dangerouslySetInnerHTML={{ __html: qrCode }} />
      </Animate>
      }
      {pinCode &&
      <p>
        Pin Code: <Animate on={pinCode} transition="FadeIn">{pinCode}</Animate>
      </p>
      }
    </div>
  );
}
