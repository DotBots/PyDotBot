import axios from 'axios';
import { useCallback, useEffect, useState } from 'react';

const DotBotRow = (props) => {

  const activate = () => {
    axios.put(`http://localhost:8000/controller/dotbots/${props.dotbot.address}`, {
      headers: {
        'Content-Type': 'application/json',
      },
    })
    .catch((error) => {
      console.error("Error:", error);
    });
  }

  return (
    <tr>
      <td>0x{`${props.dotbot.address}`}</td>
      <td>{`${props.dotbot.last_seen.toFixed(3)}`}</td>
      <td>
      {
        props.dotbot.active ? (
          <span className="badge text-bg-success">active</span>
        ) : (
          <button className="badge text-bg-primary text-light border-0" onClick={activate}>activate</button>
        )
      }
      </td>
    </tr>
  )
}

const DotBots = () => {
  const [ dotbots, setDotbots ] = useState();

  const fetchDotBots = useCallback(() => {
    axios.get(
      `http://localhost:8000/controller/dotbots`,
    )
    .then(res => {
      setDotbots(res.data);
    })
    .catch(error => {
      console.log(error);
    });
    setTimeout(() => {
      fetchDotBots();
    }, 1000);
  }, [setDotbots]
  );

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
  }, [dotbots, fetchDotBots]);

  return (
    <>
    <nav className="navbar navbar-expand-lg bg-dark">
      <div className="container-fluid">
        <a className="navbar-brand text-light" href="http://www.dotbots.org">DotBots</a>
      </div>
    </nav>
    <div className="container">
      <div className="card m-1">
        <div className="card-header">Available DotBots</div>
        <div className="card-body p-0">
            <table id="table" className="table table-striped align-middle">
              <thead>
                  <tr>
                    <th>Address</th>
                    <th>Last seen</th>
                    <th>State</th>
                  </tr>
              </thead>
              <tbody>
              {dotbots && dotbots.map(dotbot => <DotBotRow key={dotbot.address} dotbot={dotbot} />)}
              </tbody>
            </table>
        </div>
      </div>
    </div>
    </>
  );
}

export default DotBots;
