import { dotbotStatuses, dotbotBadgeStatuses } from "./utils/constants";

import { XGOActionId } from "./utils/constants";
import logger from './utils/logger';
const log = logger.child({module: 'xgo-item'});

export const XGOItem = ({dotbot, updateActive, publishCommand}) => {

  let rgbColor = "rgb(0, 0, 0)"

  const applyAction = async (action) => {
    log.info(`Applying XGO action ${action}`);
    await publishCommand(dotbot.address, dotbot.application, "xgo_action", { action: action });
  }

  return (
    <div className="accordion-item">
      <h2 className="accordion-header" id={`heading-${dotbot.address}`}>
        <button className="accordion-button collapsed" onClick={() => updateActive(dotbot.address)} type="button" data-bs-toggle="collapse" data-bs-target={`#collapse-${dotbot.address}`} aria-controls={`collapse-${dotbot.address}`}>
          <div className="d-flex" style={{ width: '100%' }}>
            <div className="me-2">
              <svg style={{ height: '12px', width: '12px'}}>
                <circle cx={5} cy={5} r={5} fill={rgbColor} opacity={`${dotbot.status === 0 ? "100%" : "30%"}`} />
              </svg>
            </div>
            <div className="me-auto">{dotbot.address}</div>
            <div className="me-2">
              <div className={`badge text-bg-${dotbotBadgeStatuses[dotbot.status]} text-light border-0`}>
                {dotbotStatuses[dotbot.status]}
              </div>
            </div>
          </div>
        </button>
      </h2>
      <div id={`collapse-${dotbot.address}`} className="accordion-collapse collapse" aria-labelledby={`heading-${dotbot.address}`} data-bs-parent="#accordion-xgo">
        <div className="accordion-body">
          <div className="d-flex mx-auto card">
            <div className="card-body p-1">
              <p className="m-0 p-0">
                <span>Actions: </span>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.SitDown)}>Sit Down</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.StandUp)}>Stand Up</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.Dance)}>Dance</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.Stretch)}>Stretch</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.Wave)}>Wave</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.Pee)}>Pee</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.Naughty)}>Naughty</button>
                <button className="btn btn-primary btn-sm m-1" onClick={async () => applyAction(XGOActionId.SquatUp)}>Squat Up</button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
