import React from "react";
import { useState } from "react";

import useInterval from "use-interval";
import { useSpring, animated } from "@react-spring/web";
import { useDrag } from "@use-gesture/react";


const speedOffset = 30;


export const Joystick = (props) => {
  const [state, setState] = useState({active: false, position: {x: 0, y: 0}});

  const [{ x, y }, set] = useSpring(() => ({ x: 0, y: 0 }));

  const bind = useDrag(async ({ active, movement: [mx, my] }) => {
    let distance = Math.sqrt(Math.pow(mx, 2) + Math.pow(my, 2));
    if (active && distance > 100) {
      return;
    }
    let newPos = { x: mx, y: my };
    setState({active: active, position: newPos});
    set({ x: active ? mx : 0, y: active ? my : 0, immediate: active });

    if (!active) {
      await props.publishCommand(props.address, props.application, "move_raw", { left_x: 0, left_y: 0, right_x: 0, right_y: 0 });
    }
  })

  const moveToSpeeds = () => {
    const dir = (128 * state.position.y / 200) * -1;
    const angle = (128 * state.position.x / 200);

    let leftSpeed = (dir + angle);
    let rightSpeed = (dir - angle);

    // Use speed offset
    if (leftSpeed > 0) {
      leftSpeed += speedOffset;
    }
    if (rightSpeed > 0) {
      rightSpeed += speedOffset;
    }
    if (leftSpeed < 0) {
      leftSpeed -= speedOffset;
    }
    if (rightSpeed < 0) {
      rightSpeed -= speedOffset;
    }

    // Clamp speeds to int8 bounds
    if (leftSpeed > 127) {
      leftSpeed = 127;
    }
    if (rightSpeed > 127) {
      rightSpeed = 127;
    }
    if (leftSpeed < -128) {
      leftSpeed = -128;
    }
    if (rightSpeed < -128) {
      rightSpeed = -128;
    }

    return { left: parseInt(leftSpeed), right: parseInt(rightSpeed) };
  };

  useInterval(async () => {
    const speeds = moveToSpeeds();
    await props.publishCommand(props.address, props.application, "move_raw", { left_x: 0, left_y: speeds.left, right_x: 0, right_y: speeds.right });
  }, state.active ? 100 : null);

  return (
    <div style={{ height: '200px', width: '200px' }}>
      <div style={{ height: '200px', width: '200px', position: "absolute" }} role="region">
        <svg style={{ height: '199px', width: '199px'}}>
            <circle cx={99} cy={99} r={98} fill="Lavender" opacity="80%" stroke="black" strokeWidth="1" />
        </svg>
      </div>
      <div style={{ position: "relative", top: "50px", left: "50px" }}>
        <animated.div {...bind()} style={{ x, y, touchAction: 'none' }} role="button">
          <svg style={{ height: '100px', width: '100px' }}>
            <defs>
              <radialGradient id={`joystickHandleGradient${props.address}`}>
                <stop offset="5%" stopColor="MediumSlateBlue" />
                <stop offset="95%" stopColor="DarkSlateBlue" />
              </radialGradient>
            </defs>
            <circle cx={50} cy={50} r={50} opacity="80%" fill={`url('#joystickHandleGradient${props.address}')`} />
          </svg>
        </animated.div>
      </div>
    </div>
  )
}
