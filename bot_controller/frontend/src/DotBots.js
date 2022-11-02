import axios from 'axios';
import { useCallback, useEffect, useState } from 'react';

const DotBotRow = (props) => {

  const updateActive = () => {
    let newAddress = props.dotbot.address;
    if (props.dotbot.address === props.activeDotbot) {
      newAddress = "0000000000000000"
    }
    axios.put(`${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbot_address`,
      {
        address: newAddress,
      },
      {
        headers: {
          'Content-Type': 'application/json',
        },
      }
    )
    .catch((error) => {
      console.error("Error:", error);
    });
  }

  return (
    <tr>
      <td>0x{`${props.dotbot.address}`}</td>
      <td>{`${props.dotbot.application}`}</td>
      <td>0x{`${props.dotbot.swarm}`}</td>
      <td>{`${props.dotbot.last_seen.toFixed(3)}`}</td>
      <td>
      {
        props.dotbot.address === props.activeDotbot ? (
          <button className="badge text-bg-success text-light border-0" onClick={updateActive}>active</button>
        ) : (
          <button className="badge text-bg-primary text-light border-0" onClick={updateActive}>activate</button>
        )
      }
      </td>
    </tr>
  )
}

const DotBots = () => {
  const [ dotbots, setDotbots ] = useState();
  const [ activeDotbot, setActiveDotbot ] = useState("0000000000000000");

  const fetchDotBots = useCallback(() => {
    axios.get(
      `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbots`,
    )
    .then(res => {
      setDotbots(res.data);
    })
    .catch(error => {
      console.log(error);
    });
    axios.get(
      `${process.env.REACT_APP_DOTBOTS_BASE_URL}/controller/dotbot_address`,
    )
    .then(res => {
      setActiveDotbot(res.data.address);
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
                    <th>Application</th>
                    <th>Swarm ID</th>
                    <th>Last seen</th>
                    <th>State</th>
                  </tr>
              </thead>
              <tbody>
              {dotbots && dotbots.map(dotbot => <DotBotRow key={dotbot.address} dotbot={dotbot} activeDotbot={activeDotbot}/>)}
              </tbody>
            </table>
        </div>
      </div>
    </div>
    </>
  );
}

export default DotBots;
