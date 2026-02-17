import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useEffect, useState } from "react";

import RestApp from "./RestApp";
import QrKeyApp from "./QrKeyApp";

const App = () => {
  const [useQrKey, setUseQrKey] = useState(false);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const qrKeyParam = searchParams.get('use_qrkey');
    if (qrKeyParam && qrKeyParam.toLowerCase() === 'true') {
      setUseQrKey(true);
      localStorage.setItem('use_qrkey', 'true');
    } else if (!qrKeyParam || (qrKeyParam && qrKeyParam.toLowerCase() === 'false')) {
      setUseQrKey(false);
      localStorage.setItem('use_qrkey', 'false');
    } else if (localStorage.getItem('use_qrkey') === 'true') {
      setUseQrKey(true);
    } else {
      localStorage.setItem('use_qrkey', 'false');
    }
  }, [searchParams, setUseQrKey]
  );

  return (
    <>
    {useQrKey ? <QrKeyApp /> : <RestApp />}
    </>
  );
}

export default App;
