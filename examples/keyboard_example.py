import keyboard
from dotbot.orchestrator import gateway

# TODO: update example

def onkeypress(event):
    # print(event.name)

    if event.name == "enter":
        gateway.command_move(0, 0)
    elif event.name == "left":
        gateway.command_move(0, 1)
    elif event.name == "right":
        gateway.command_move(0, -1)
    elif event.name == "up":
        gateway.command_move(1, 0)
    elif event.name == "down":
        gateway.command_move(-1, 0)

keyboard.on_press(onkeypress)

#Use ctrl+c to stop
while True:
    pass