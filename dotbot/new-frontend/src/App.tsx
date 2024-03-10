import React from 'react'
import useDotBots from './useDotBots'
import { DotBotModel } from './models'

function App() {

  const { dotBots } = useDotBots();

  return (
    <>
      <div>
        { dotBots && dotBots.map((dotBot: DotBotModel, index: number) => {
          return (
            <div key={index}>
              <div>DotBot {index + 1}</div>
              <div>Address: {dotBot.address}</div>
              <div>Position: {dotBot.lh2_position && <b>{dotBot.lh2_position.x}, {dotBot.lh2_position.y}</b>}</div>
            </div>
          )
        })}
      </div>
    </>
  )
}

export default App
